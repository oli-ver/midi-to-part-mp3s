import os
import shutil
import subprocess
import tempfile
import unittest

import mido  # type: ignore
import numpy

# allow to import modules from parent dir (https://stackoverflow.com/a/33532002/2641951)
from inspect import getsourcefile
import os.path as path
import sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
import midi_to_part_mp3s  # noqa: E402

BRAHMS = "./tests/fixtures/Brahms-Da-unten-im-Tale.mid"
SCHUMANN = "./tests/fixtures/Schumann-op67-4.mid"


def load(file_path):
    return midi_to_part_mp3s.ensure_midi_well_formatted(mido.MidiFile(file_path))


def events(track, *types):
    """(absolute tick, message) of the messages of the given types"""
    result = []
    tick = 0
    for message in track:
        tick += message.time
        if message.type in types:
            result.append((tick, message))
    return result


def first_note_tick(midi_data):
    return min(events(track, 'note_on')[0][0] for track in midi_data.tracks
               if events(track, 'note_on'))


class TestCountIn(unittest.TestCase):
    def test_separate_tempo_map_keeps_time_signature_positions(self):
        # Brahms has no separate tempo map and starts with a 1/4 pickup bar
        self.assertEqual(midi_to_part_mp3s.time_signatures(load(BRAHMS)),
                         [(0, 1, 4), (480, 3, 4), (10560, 2, 4)])

    def test_count_in_uses_the_full_bar_after_a_pickup(self):
        self.assertEqual(midi_to_part_mp3s.count_in_signature(load(BRAHMS)), (3, 4))
        self.assertEqual(midi_to_part_mp3s.count_in_signature(load(SCHUMANN)), (3, 4))

    def test_count_in_moves_the_music_one_bar_later(self):
        original = load(SCHUMANN)
        moved = midi_to_part_mp3s.add_count_in(original)
        bar = 3 * original.ticks_per_beat
        self.assertEqual(first_note_tick(moved), first_note_tick(original) + bar)
        # Schumann starts at 60 beats per minute, so a 3/4 bar takes 3 seconds
        self.assertAlmostEqual(moved.length, original.length + 3, places=3)
        # the tempo at the start stays, so the count-in is in the tempo of the piece
        self.assertEqual(events(moved.tracks[0], 'set_tempo')[0][0], 0)
        self.assertEqual(midi_to_part_mp3s.time_signatures(moved)[:2],
                         [(0, 3, 4), (bar, 3, 4)])
        # the original is not changed
        self.assertEqual(first_note_tick(original), 0)

    def test_count_in_after_pickup_bar(self):
        moved = midi_to_part_mp3s.add_count_in(load(BRAHMS))
        self.assertEqual(midi_to_part_mp3s.time_signatures(moved),
                         [(0, 3, 4), (1440, 1, 4), (1920, 3, 4), (12000, 2, 4)])
        self.assertEqual(first_note_tick(moved), 1440)

    def test_count_in_clicks(self):
        moved = midi_to_part_mp3s.add_count_in(load(SCHUMANN))
        clicks = events(midi_to_part_mp3s.click_track(moved, True, False), 'note_on')
        beat = moved.ticks_per_beat
        self.assertEqual([(tick, message.note, message.velocity) for tick, message in clicks], [
            (0, midi_to_part_mp3s.CLICK_ACCENT_NOTE, midi_to_part_mp3s.COUNT_IN_VELOCITY),
            (beat, midi_to_part_mp3s.CLICK_NOTE, midi_to_part_mp3s.COUNT_IN_VELOCITY),
            (2 * beat, midi_to_part_mp3s.CLICK_NOTE, midi_to_part_mp3s.COUNT_IN_VELOCITY)])
        self.assertTrue(all(message.channel == midi_to_part_mp3s.PERCUSSION_CHANNEL
                            for _, message in clicks))

    def test_click_throughout_follows_the_time_signatures(self):
        midi_data = load(BRAHMS)
        clicks = events(midi_to_part_mp3s.click_track(midi_data, False, True), 'note_on')
        accents = [tick for tick, message in clicks
                   if message.note == midi_to_part_mp3s.CLICK_ACCENT_NOTE]
        # pickup bar, then 3/4 bars of 1440 ticks, then 2/4 bars from tick 10560
        self.assertEqual(accents[:3], [0, 480, 1920])
        self.assertIn(10560, accents)
        self.assertTrue(all(message.velocity == midi_to_part_mp3s.CLICK_VELOCITY
                            for _, message in clicks))
        self.assertLess(clicks[-1][0], midi_to_part_mp3s.last_note_tick(midi_data))


class TestCountInConversion(unittest.TestCase):
    def setUp(self):
        self.output = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.output, True)

    def convert(self, *options):
        output = os.path.join(self.output, '-'.join(options) or 'plain')
        self.assertEqual(subprocess.run(
            ["./midi-to-part-mp3s", "-f", BRAHMS, "-in", "76", "-o", output, *options],
            capture_output=True).returncode, 0)
        return output

    def test_files_start_with_count_in(self):
        plain = self.convert()
        counted = self.convert("--count-in", "--click")
        self.assertEqual(sorted(os.listdir(plain)), sorted(os.listdir(counted)))
        # 120 beats per minute, so the 3/4 count-in bar takes 1.5 seconds
        beat_samples = midi_to_part_mp3s.SAMPLE_RATE // 2
        for file_name in os.listdir(plain):
            without = midi_to_part_mp3s.read_audio(os.path.join(plain, file_name))
            with_count_in = midi_to_part_mp3s.read_audio(os.path.join(counted, file_name))
            self.assertAlmostEqual(with_count_in.shape[1] - without.shape[1],
                                   3 * beat_samples, delta=beat_samples / 10, msg=file_name)
            # each of the three count-in beats starts with a click that peaks well
            # above the level of the music after it
            music_rms = numpy.sqrt((with_count_in[:, 3 * beat_samples:] ** 2).mean())
            for beat in range(3):
                start = beat * beat_samples
                click = numpy.abs(with_count_in[:, start:start + beat_samples // 4]).max()
                self.assertGreater(click, 2 * music_rms,
                                   msg="{} beat {}".format(file_name, beat))


if __name__ == '__main__':
    unittest.main()
