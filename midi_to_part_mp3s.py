#!/usr/bin/env python3
import argparse
import os
import sys
import shutil
import subprocess
from typing import List, Dict

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
# instrument choices based off advice given here: http://www3.cpdl.org/wiki/index.php/User:Robert_Urmann
MAPPING = {
    "soprano": 76,  # pan flute
    "alto": 75,  # recorder
    "tenor": 49,  # string ensemble 1
    "bass": 50  # string ensemble 2
}
args = None


class Part:
    def __init__(self, name: str = '', midi: str = '', midi_filepath: str = ''):
        self.name = name
        self.midi = midi
        self.midi_filepath = midi_filepath
        convert_midi_to_mp3(midi_filepath)
        self.rms_db, self.peak_db = measure_level(self.mp3_filepath())

    def mp3_filepath(self) -> str:
        return self.midi_filepath.replace(".midi", ".mp3")


def check_format(file_path: str) -> str:
    """If the format is midi, proceed. If the format is MusicXML, convert to midi.

    Arguments:
        file_path {[str]} -- path of the file to convert

    Raises:
        NameError: Raised if trying to convert a format not supported by the script

    Returns:
        str -- midi file name (original or converted midi file)
    """
    if file_path.endswith('.mid') or file_path.endswith('.midi'):
        return file_path
    elif file_path.endswith('.mxl') or file_path.endswith('.musicxml'):
        return convert_music_xml_to_midi(file_path)
    else:
        raise NameError(
            'The application currently only supports midi or MusicXML format')


def convert_music_xml_to_midi(file_path: str) -> str:
    """Converts a MusicXML file to midi

    Arguments:
        file_path {str} -- file path of the the MusicXML file

    Returns:
        str -- path of the converted midi file after conversion
    """
    converted_file_path = args.output + '/temp.midi'
    score: music21.stream.Score = music21.converter.parse(file_path)
    midi_file = music21.midi.translate.streamToMidiFile(score)
    midi_file.open(converted_file_path, 'wb')
    midi_file.write()
    midi_file.close()
    return converted_file_path


def track_names(midi_data) -> List[str]:
    return list(map(lambda track: track.name, midi_data.tracks))


def instrument_number_for_part(part: str) -> int:
    """Fetches the instrument index from the mapping. In case of an instrument
    parameter this instrument is returned instead of the default mapping

    Arguments:
        part {str} -- name of the part

    Returns:
        int -- integer index of an instrument
    """
    global args
    if (args.instrument != None):
        return args.instrument
    else:
        return MAPPING[part]


def generate_solo_parts(midi_data: mido.MidiFile, track_numbers: List[int], part_name: str, instrument_number: int) -> Part:
    """Generates a solo part and returns a Part object describing it

    Arguments:
        midi_data {mido.MidiFile} -- original midi data
        track_numbers {List[int]} -- numbers of the tracks to include in the solo parts
        part_name {str} -- name of the past
        instrument_number {int} -- id of the instrument in the configured soundfont

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
    new_file_path = "{}/{}.midi".format(args.output, part_name)
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


def loudness_normalizing_gain(part: Part) -> float:
    """Amplitude factor that brings the part to a common loudness (0 dBFS RMS)"""
    if part.rms_db is None:
        return 0.0
    return 10 ** (-part.rms_db / 20)


def mix_parts(solo_parts: List[Part], gains: List[float], output_file_path: str) -> None:
    """Mixes the parts with the given amplitude factors. All factors are scaled
    together so the mix cannot clip, which keeps the ratios between the parts.
    """
    worst_case_peak = sum(gain * 10 ** (part.peak_db / 20)
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
    rest_power = len(other_voices) + \
        (instrumental_volume ** 2 if has_instrumental else 0)
    other_gain = 1.0
    if rest_power > 0:
        other_gain = 1 / (10 ** (voice_margin_db / 20) * rest_power ** 0.5)

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


def generate_accompaniment(own_part, solo_parts) -> None:
    gains = accompaniment_gains(own_part, solo_parts, args.voice_margin,
                                args.instrumental_volume)
    output_file_path = "{}/{} with accompaniment.mp3".format(
        args.output, own_part.name)
    mix_parts(solo_parts, gains, output_file_path)


def generate_full_mp3(solo_parts: List[Part]) -> None:
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


def separate_tracks_into_mp3s(args: argparse.Namespace, midifile_path: str) -> None:
    midi_data: mido.MidiFile = ensure_midi_well_formatted(
        mido.MidiFile(midifile_path))
    solo_parts: List[Part] = []
    voices: list = create_voices()
    add_accompaniment(voices)
    for part_name, track_numbers, instrument in voices:
        solo_part: Part = generate_solo_parts(
            midi_data, track_numbers, part_name, instrument)
        solo_parts.append(solo_part)

    part: Part
    for part in solo_parts:
        generate_accompaniment(part, solo_parts)

    generate_full_mp3(solo_parts)


def create_voices() -> list:
    """Creates a nested list of the voices with their assigned midi track number

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
                instrument = instrument_number_for_part(sung_part)
                voice = [sung_part + ' ' + str(i+1), tracks, instrument]
                voices.append(voice)
    return voices


def add_accompaniment(voices: list) -> None:
    """Edits the voices list to include the accompaniment voice

    Arguments:
        voices {list} -- list of voices and their assigned midi track numbers
    """
    if args.instrumental_accompaniment:
        voices.append(
            ['accompaniment', args.instrumental_accompaniment, None])


def cleanup() -> None:
    remove_temporary_midifiles()


def prepare_output_directory() -> None:
    """ Ensures an empty output directory is available"""
    if os.path.exists(args.output):
        shutil.rmtree(args.output)

    os.makedirs(args.output)




def remove_temporary_midifiles() -> None:
    midi_file: str
    for midi_file in os.listdir(args.output):
        if midi_file.endswith('.midi'):
            os.unlink(os.path.join(args.output, midi_file))


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


def main(sys_args):
    parser = get_parser()
    global args
    args = parser.parse_args(sys_args)
    set_defaults(args)
    prepare_output_directory()
    midi_file_path = check_format(args.file_path)
    separate_tracks_into_mp3s(args, midi_file_path)
    cleanup()


if __name__ == "__main__":
    main(sys.argv[1:])
