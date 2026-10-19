#!/usr/bin/env python3
import argparse
import os
import sys
import shutil
import subprocess
from typing import List, Dict

import numpy  # type: ignore
import sox  # type: ignore
import mido  # type: ignore
import music21  # type: ignore

output_directory = './output'
soundfont_path = "./soundfonts/timbres-of-heaven.sf2"
sung_parts = ['soprano', 'alto', 'bass', 'tenor']
# the practised voice is mixed this many dB above all other parts together
DEFAULT_VOICE_MARGIN_DB = 8.0
# peak level the mixes are scaled to, safely below clipping
MIX_PEAK_AMPLITUDE = 0.9
SAMPLE_RATE = 44100
# the balance between the practised voice and the rest is checked in steps of
# BALANCE_HOP_S and judged over BALANCE_WINDOW_S, so single notes don't pump
BALANCE_HOP_S = 0.05
BALANCE_WINDOW_S = 0.4
# the other parts are lowered by at most this much, so they never drop out
MAX_BALANCE_REDUCTION_DB = 12.0
# rendering a part counts as one unit of work for the progress report, the mixes
# take about this many units per mixed part (measured with the test fixtures)
ACCOMPANIMENT_MIX_UNITS_PER_PART = 0.6
FULL_MIX_UNITS_PER_PART = 0.4
# instrument choices based off advice given here: http://www3.cpdl.org/wiki/index.php/User:Robert_Urmann
MAPPING = {
    "soprano": 76,  # pan flute
    "alto": 75,  # recorder
    "tenor": 49,  # string ensemble 1
    "bass": 50  # string ensemble 2
}


class Part:
    def __init__(self, name: str = '', midi: str = '', midi_filepath: str = ''):
        self.name = name
        self.midi = midi
        self.midi_filepath = midi_filepath
        convert_midi_to_mp3(midi_filepath)
        self.rms_db, self.peak_db = measure_level(self.mp3_filepath())

    def mp3_filepath(self) -> str:
        return self.midi_filepath.replace(".midi", ".mp3")


def check_format(file_path: str, output_dir: str) -> str:
    """If the format is midi, proceed. If the format is MusicXML, convert to midi.

    Arguments:
        file_path {[str]} -- path of the file to convert
        output_dir {str} -- folder the converted midi file is written to

    Raises:
        NameError: Raised if trying to convert a format not supported by the script

    Returns:
        str -- midi file name (original or converted midi file)
    """
    if file_path.endswith('.mid') or file_path.endswith('.midi'):
        return file_path
    elif file_path.endswith('.mxl') or file_path.endswith('.musicxml'):
        return convert_music_xml_to_midi(file_path, output_dir)
    else:
        raise NameError(
            'The application currently only supports midi or MusicXML format')


def convert_music_xml_to_midi(file_path: str, output_dir: str) -> str:
    """Converts a MusicXML file to midi

    Arguments:
        file_path {str} -- file path of the the MusicXML file
        output_dir {str} -- folder the converted midi file is written to

    Returns:
        str -- path of the converted midi file after conversion
    """
    converted_file_path = output_dir + '/temp.midi'
    score: music21.stream.Score = music21.converter.parse(file_path)
    midi_file = music21.midi.translate.streamToMidiFile(score)
    midi_file.open(converted_file_path, 'wb')
    midi_file.write()
    midi_file.close()
    return converted_file_path


def track_names(midi_data) -> List[str]:
    return list(map(lambda track: track.name, midi_data.tracks))


def instrument_number_for_part(part: str, instrument: int = None) -> int:
    """Fetches the instrument index from the mapping. In case of an instrument
    parameter this instrument is returned instead of the default mapping

    Arguments:
        part {str} -- name of the part
        instrument {int} -- instrument for all voices, None for the default mapping

    Returns:
        int -- integer index of an instrument
    """
    if (instrument != None):
        return instrument
    else:
        return MAPPING[part]


def generate_solo_parts(midi_data: mido.MidiFile, track_numbers: List[int], part_name: str, instrument_number: int, output_dir: str) -> Part:
    """Generates a solo part and returns a Part object describing it

    Arguments:
        midi_data {mido.MidiFile} -- original midi data
        track_numbers {List[int]} -- numbers of the tracks to include in the solo parts
        part_name {str} -- name of the past
        instrument_number {int} -- id of the instrument in the configured soundfont
        output_dir {str} -- folder the midi and mp3 files are written to

    Returns:
        Part -- generated Part object
    """
    midi: mido.MidiFile = mido.MidiFile()
    midi.ticks_per_beat: int = midi_data.ticks_per_beat

    track_number: int
    for track_number in track_numbers:
        midi.tracks.append(midi_data.tracks[track_number])

    if part_name != 'accompaniment':
        change_instrument(midi, instrument_number)
    new_file_path = "{}/{}.midi".format(output_dir, part_name)
    midi.save(new_file_path)

    part = Part(name=part_name, midi=midi, midi_filepath=new_file_path)

    return part


def convert_midi_to_mp3(midifile_path: str) -> None:
    """Converts the midi file to mp3 format

    Arguments:
        midifile_path {str} -- path to the midi file

    Returns:
        None -- does not return anything. The file is created on the file system using fluidsynth
    """
    output_base_filename = os.path.splitext(midifile_path)[0]
    # Arguments are passed as lists (no shell), so file names cannot inject commands
    fluidsynth = subprocess.Popen(
        ["fluidsynth", "-r", "44100", "-R", "1", "-E", "little", "-T", "raw",
         "-F", "-", "-O", "s16", soundfont_path, midifile_path],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    lame = subprocess.run(
        ["lame", "--quiet", "--signed", "-s", "44100", "-r", "-",
         "{}.mp3".format(output_base_filename)],
        stdin=fluidsynth.stdout, check=False)
    fluidsynth.stdout.close()
    if fluidsynth.wait() != 0 or lame.returncode != 0:
        raise RuntimeError(
            "Conversion of {} to mp3 failed".format(midifile_path))


def measure_level(mp3_filepath: str):
    """Measures the loudness of the audible parts of an mp3 file. Rests are
    removed first, so a voice with many rests is not considered quiet.

    Arguments:
        mp3_filepath {str} -- path to the mp3 file

    Returns:
        tuple -- RMS level and peak level in dBFS, (None, None) if silent
    """
    result = subprocess.run(
        ["sox", mp3_filepath, "-n", "silence", "1", "0.05", "0.1%",
         "-1", "0.05", "0.1%", "stats"],
        capture_output=True, text=True, check=False)
    levels = {}
    for line in result.stderr.splitlines():
        for key in ("RMS lev dB", "Pk lev dB"):
            if line.startswith(key):
                try:
                    levels[key] = float(line.split()[3])
                except (IndexError, ValueError):
                    pass
    if "RMS lev dB" not in levels or "Pk lev dB" not in levels:
        return None, None
    return levels["RMS lev dB"], levels["Pk lev dB"]


def db_to_amplitude(db: float) -> float:
    """Converts a level difference in decibels into the factor the audio samples
    are multiplied with, e.g. +6 dB = 2x, -20 dB = 0.1x. Decibels compare energies
    (10 * log10) and energy is the square of the sample values, hence 20 instead
    of 10. See docs/voice-loudness.md for the full explanation.
    """
    return 10 ** (db / 20)


def loudness_normalizing_gain(part: Part) -> float:
    """Amplitude factor that brings the part to a common loudness (0 dBFS RMS)"""
    if part.rms_db is None:
        return 0.0
    # a part measured at e.g. -46 dB needs +46 dB to reach 0 dB
    return db_to_amplitude(-part.rms_db)


def mix_parts(solo_parts: List[Part], gains: List[float], output_file_path: str) -> None:
    """Mixes the parts with the given amplitude factors. All factors are scaled
    together so the mix cannot clip, which keeps the ratios between the parts.
    """
    worst_case_peak = sum(gain * db_to_amplitude(part.peak_db)
                          for part, gain in zip(solo_parts, gains)
                          if part.peak_db is not None)
    scale = MIX_PEAK_AMPLITUDE / worst_case_peak if worst_case_peak > 0 else 1.0
    combiner = sox.Combiner()
    # docs https://pysox.readthedocs.io/en/latest/api.html
    combiner.build([part.mp3_filepath() for part in solo_parts], output_file_path,
                   'mix', [gain * scale for gain in gains])


def change_instrument(midi_data: mido.MidiFile, program_number: int):
    """Changes the instrument in all tracks of the given midi_data
    object to the instrument identified by program_number

    Arguments:
        midi_data {mido.MidiFile} -- midi data object
        program_number {int} -- instrument identifier
    """
    track: mido.MidiTrack
    for track in midi_data.tracks:
        found = None
        message: mido.Message
        for message in track:
            if message.type == 'program_change':
                found = True
                message.program = program_number
        if not found:
            program_change_message = mido.Message(
                'program_change', program=program_number)
            track.insert(0, program_change_message)


def accompaniment_gains(own_part: Part, solo_parts: List[Part],
                        voice_margin_db: float, instrumental_volume: float) -> List[float]:
    """Calculates the amplitude factors for a practice mix. All parts are first
    brought to the same loudness. The other parts are then lowered so that the
    practised voice is voice_margin_db louder than all of them together, no matter
    how many voices there are. The instrumental accompaniment is instrumental_volume
    times as loud as each other voice.

    Returns:
        List[float] -- amplitude factor per part, in the order of solo_parts
    """
    other_voices = [part for part in solo_parts if part.name not in (
        own_part.name, 'accompaniment') and part.rms_db is not None]
    has_instrumental = any(part.name == 'accompaniment' and part.rms_db is not None
                           for part in solo_parts)
    # energies of independent parts add up: after normalizing, each other voice
    # counts 1, the accompaniment instrumental_volume squared (energy = amplitude^2)
    rest_power = len(other_voices) + \
        (instrumental_volume ** 2 if has_instrumental else 0)
    other_gain = 1.0
    if rest_power > 0:
        # lower the rest by the margin and by its summed energy, e.g. 3 other
        # voices: 8 dB + 4.8 dB, as 10 * log10(3) = 4.8 dB
        other_gain = 1 / (db_to_amplitude(voice_margin_db) * rest_power ** 0.5)

    gains = []
    for part in solo_parts:
        gain = loudness_normalizing_gain(part)
        if part.name == own_part.name:
            gains.append(gain if part.rms_db is not None else 1.0)
        elif part.name == 'accompaniment':
            gains.append(gain * other_gain * instrumental_volume)
        else:
            gains.append(gain * other_gain)
    return gains


def read_audio(mp3_filepath: str) -> numpy.ndarray:
    """Decodes an audio file to a float array of shape (channels, samples)"""
    raw = subprocess.run(
        ["sox", mp3_filepath, "-t", "raw", "-e", "floating-point", "-b", "32",
         "-c", "2", "-r", str(SAMPLE_RATE), "-"],
        capture_output=True, check=True).stdout
    return numpy.frombuffer(raw, dtype=numpy.float32).reshape(-1, 2).T


def write_mp3(samples: numpy.ndarray, output_file_path: str) -> None:
    """Encodes a float array of shape (channels, samples) as mp3"""
    pcm = (numpy.clip(samples, -1.0, 1.0) * 32767).astype('<i2').T.tobytes()
    subprocess.run(["lame", "--quiet", "--signed", "-s", str(SAMPLE_RATE), "-r", "-",
                    output_file_path], input=pcm, check=True)


def _moving_average(values: numpy.ndarray, width: int) -> numpy.ndarray:
    return numpy.convolve(values, numpy.ones(width) / width, mode='same')


def balance_curve(own: numpy.ndarray, rest: numpy.ndarray, voice_margin_db: float) -> numpy.ndarray:
    """Calculates a time dependent factor for the other parts. Wherever the
    practised voice sings, the other parts are lowered just as far as needed to
    keep the practised voice voice_margin_db above them, e.g. when it sings piano
    while the others sing forte. Elsewhere the factor is 1, so the dynamics of the
    score are kept as long as they don't cover the practised voice.

    Arguments:
        own {numpy.ndarray} -- practised voice, shape (channels, samples)
        rest {numpy.ndarray} -- sum of the other parts, same shape

    Returns:
        numpy.ndarray -- factor per sample for the other parts, between 0 and 1
    """
    hop = int(SAMPLE_RATE * BALANCE_HOP_S)
    width = max(1, int(BALANCE_WINDOW_S / BALANCE_HOP_S))
    frames = own.shape[1] // hop
    if frames == 0:
        return numpy.ones(own.shape[1])

    def frame_power(signal):
        power = (signal[:, :frames * hop] ** 2).mean(axis=0)
        return _moving_average(power.reshape(frames, hop).mean(axis=1), width)

    own_power = frame_power(own)
    rest_power = frame_power(rest)
    # powers are energies, so dB convert with 10 here (not 20), see docs/voice-loudness.md
    allowed_rest_power = own_power / 10 ** (voice_margin_db / 10)
    singing = own_power > own_power.max() * 1e-4
    factor = numpy.ones(frames)
    too_loud = singing & (rest_power > allowed_rest_power)
    # the factor multiplies samples, and energy is samples squared, hence the root
    factor[too_loud] = numpy.sqrt(allowed_rest_power[too_loud] / rest_power[too_loud])
    factor = numpy.maximum(factor, db_to_amplitude(-MAX_BALANCE_REDUCTION_DB))
    # lower a little earlier and recover a little later than needed, then smooth
    # the transitions so the other parts don't jump in volume
    padded = numpy.pad(factor, width, mode='edge')
    factor = numpy.lib.stride_tricks.sliding_window_view(
        padded, 2 * width + 1).min(axis=1)
    factor = _moving_average(numpy.pad(factor, width, mode='edge'), width)[width:-width]
    frame_centers = (numpy.arange(frames) + 0.5) * hop
    return numpy.interp(numpy.arange(own.shape[1]), frame_centers, factor)


def generate_accompaniment(args: argparse.Namespace, own_part, solo_parts) -> None:
    gains = accompaniment_gains(own_part, solo_parts, args.voice_margin,
                                args.instrumental_volume)
    output_file_path = "{}/{} with accompaniment.mp3".format(
        args.output, own_part.name)

    signals = [read_audio(part.mp3_filepath()) for part in solo_parts]
    length = max(signal.shape[1] for signal in signals)
    own = numpy.zeros((2, length), dtype=numpy.float32)
    rest = numpy.zeros((2, length), dtype=numpy.float32)
    for part, gain, signal in zip(solo_parts, gains, signals):
        target = own if part.name == own_part.name else rest
        target[:, :signal.shape[1]] += gain * signal
    mix = own + rest * balance_curve(own, rest, args.voice_margin)
    peak = numpy.abs(mix).max()
    if peak > 0:
        mix *= MIX_PEAK_AMPLITUDE / peak
    write_mp3(mix, output_file_path)


def generate_full_mp3(args: argparse.Namespace, solo_parts: List[Part]) -> None:
    # all voices equally loud, the accompaniment as configured
    gains = [loudness_normalizing_gain(part) *
             (args.instrumental_volume if part.name == 'accompaniment' else 1.0)
             for part in solo_parts]
    output_file_path = "{}/all.mp3".format(args.output)
    mix_parts(solo_parts, gains, output_file_path)


def has_separate_tempo_map(track0: mido.midifiles.tracks.MidiTrack) -> bool:
    return not any(event.type == "note_on" for event in track0)


def separate_out_tempo_map(midi_data: mido.MidiFile) -> mido.MidiFile:
    tempo_map = []
    track1 = []

    for event in midi_data.tracks[0]:
        if event.is_meta:
            if event.type in ["instrument_name", "key_signature"]:
                track1.append(event)
            else:
                track1.append(event)
                tempo_map.append(event)
        else:
            track1.append(event)

    midi = mido.MidiFile()
    midi.ticks_per_beat = midi_data.ticks_per_beat

    midi.tracks.append(tempo_map)
    midi.tracks.append(track1)
    for track in midi_data.tracks[1:]:
        midi.tracks.append(track)

    return midi


def ensure_midi_well_formatted(midi_data: mido.MidiFile) -> mido.MidiFile:
    if has_separate_tempo_map(midi_data.tracks[0]):
        return midi_data
    else:
        return separate_out_tempo_map(midi_data)


def separate_tracks_into_mp3s(args: argparse.Namespace, midifile_path: str,
                              progress=None) -> None:
    """Generates the mp3s. progress is called as progress(done_units, total_units,
    audio_seconds) at the start and after every step."""
    midi_data: mido.MidiFile = ensure_midi_well_formatted(
        mido.MidiFile(midifile_path))
    solo_parts: List[Part] = []
    voices: list = create_voices(args)
    add_accompaniment(args, voices)
    accompaniment_units = ACCOMPANIMENT_MIX_UNITS_PER_PART * len(voices)
    full_mix_units = FULL_MIX_UNITS_PER_PART * len(voices)
    # one rendering and one mix per part and the full mix
    total_units = len(voices) * (1 + accompaniment_units) + full_mix_units
    done_units = 0.0

    def report(units: float) -> None:
        nonlocal done_units
        done_units += units
        if progress:
            progress(done_units, total_units, midi_data.length)

    report(0)
    for part_name, track_numbers, instrument in voices:
        solo_part: Part = generate_solo_parts(
            midi_data, track_numbers, part_name, instrument, args.output)
        solo_parts.append(solo_part)
        report(1)

    part: Part
    for part in solo_parts:
        generate_accompaniment(args, part, solo_parts)
        report(accompaniment_units)

    generate_full_mp3(args, solo_parts)
    report(full_mix_units)


def create_voices(args: argparse.Namespace) -> list:
    """Creates a nested list of the voices with their assigned midi track number

    Arguments:
        args {argparse.Namespace} -- arguments with the track numbers per voice

    Returns:
        List[List] -- list of voices and their assigned midi track numbers
    """
    voices: List[List] = []
    tempo_map_track_number = 0
    sung_part: str
    for sung_part in sung_parts:
        voice_midi_tracks = vars(args)[sung_part]
        if(voice_midi_tracks):
            for i in range(len(voice_midi_tracks)):
                tracks = []
                track_id = voice_midi_tracks[i]
                tracks.append(tempo_map_track_number)
                tracks.append(track_id)
                instrument = instrument_number_for_part(
                    sung_part, args.instrument)
                voice = [sung_part + ' ' + str(i+1), tracks, instrument]
                voices.append(voice)
    return voices


def add_accompaniment(args: argparse.Namespace, voices: list) -> None:
    """Edits the voices list to include the accompaniment voice

    Arguments:
        args {argparse.Namespace} -- arguments with the accompaniment tracks
        voices {list} -- list of voices and their assigned midi track numbers
    """
    if args.instrumental_accompaniment:
        voices.append(
            ['accompaniment', args.instrumental_accompaniment, None])


def cleanup(output_dir: str) -> None:
    remove_temporary_midifiles(output_dir)


def prepare_output_directory(output_dir: str) -> None:
    """ Ensures an empty output directory is available"""
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir)




def remove_temporary_midifiles(output_dir: str) -> None:
    midi_file: str
    for midi_file in os.listdir(output_dir):
        if midi_file.endswith('.midi'):
            os.unlink(os.path.join(output_dir, midi_file))


def set_defaults(args: argparse.Namespace) -> None:
    """Sets the soprano, alto, tenor and bass voices
    to the default tracks 1, 2, 3 and 4, if no track has been defined.
    This allows a SSAA or TTBB API setting without the need to overwrite
    defaults, i.e.:
    midi-to-part-mp3s your-midi.mid --soprano 1 2 --alto 3 4
    midi-to-part-mp3s your-midi.mid --tenor 1 2 --bass 3 4

    Arguments:
        args {argparse.Namespace} -- Original arguments

    Returns:
        None -- The args will be overwritten in the original args object
    """
    if (args.soprano == None and args.alto == None and
            args.tenor == None and args.bass == None):
        args.soprano = [1]
        args.alto = [2]
        args.tenor = [3]
        args.bass = [4]
    else:
        if args.soprano:
            args.soprano = [int(track) for track in args.soprano.split(',')]
        if args.alto:
            args.alto = [int(track) for track in args.alto.split(',')]
        if args.tenor:
            args.tenor = [int(track) for track in args.tenor.split(',')]
        if args.bass:
            args.bass = [int(track) for track in args.bass.split(',')]


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--soprano", type=str,
                        help='comma separated list of midi track IDs, defaults to "1"')
    parser.add_argument("-a", "--alto", type=str,
                        help='comma separated list of midi track IDs, defaults to "2"')
    parser.add_argument("-t", "--tenor", type=str,
                        help='comma separated list of midi track IDs, defaults to "3"')
    parser.add_argument("-b", "--bass", type=str,
                        help='comma separated list of midi track IDs, defaults to "4"')
    parser.add_argument("-in", "--instrument", type=int,
                        help=('instrument that should be used for all voices instead \
                              of the advice given at cpdl.org'))
    parser.add_argument("-iv", "--instrumental-volume",
                        help="loudness of the instrumental accompaniment relative to each \
                              other voice, defaults to 2.0", type=float, default=2.0)
    parser.add_argument("-m", "--voice-margin", type=float, default=DEFAULT_VOICE_MARGIN_DB,
                        help="how many dB the practised voice is louder than all other parts \
                              together, defaults to {}".format(DEFAULT_VOICE_MARGIN_DB))
    parser.add_argument("-i", "--instrumental-accompaniment", help='midi tracks that \
          appear in all accompaniment mp3s e.g. piano or orchestra', nargs='+',
                        type=int, default=[])
    parser.add_argument("-o", "--output", type=str, default=output_directory,
                        help="Output folder for the files. Defaults to './output'")
    requiredNamed = parser.add_argument_group('mandatory argument')
    requiredNamed.add_argument("-f", "--file-path", required=True,
                               help='Input file to generate the tracks from. Can be Midi or \
                            MusicXML (.mid, .midi, .mxl, .musicxml)')
    return parser


def convert(args: argparse.Namespace, progress=None) -> None:
    """Generates the practice mp3s for the given arguments. Everything the
    conversion needs is passed in, so several conversions can run at once.

    Arguments:
        args {argparse.Namespace} -- arguments as returned by get_parser and set_defaults
        progress -- optional callback, see separate_tracks_into_mp3s
    """
    prepare_output_directory(args.output)
    midi_file_path = check_format(args.file_path, args.output)
    separate_tracks_into_mp3s(args, midi_file_path, progress)
    cleanup(args.output)


def main(sys_args, progress=None):
    parser = get_parser()
    args = parser.parse_args(sys_args)
    set_defaults(args)
    convert(args, progress)


if __name__ == "__main__":
    main(sys.argv[1:])
