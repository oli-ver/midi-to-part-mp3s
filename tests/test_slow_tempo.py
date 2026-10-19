import os
import shutil
import unittest

import mido  # type: ignore
import sox  # type: ignore

# allow to import modules from parent dir (https://stackoverflow.com/a/33532002/2641951)
from inspect import getsourcefile
import os.path as path
import sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
import midi_to_part_mp3s

FIXTURE = "./tests/fixtures/Brahms-Da-unten-im-Tale.mid"
OUTPUT = "./output-slow-tempo"


def tempos(midi_data):
    return [message.tempo for track in midi_data.tracks for message in track
            if message.type == 'set_tempo']


class TestScaleTempo(unittest.TestCase):
    def test_tempo_events_are_scaled(self):
        midi_data = mido.MidiFile(FIXTURE)
        scaled = midi_to_part_mp3s.scale_tempo(midi_data, 0.75)
        self.assertEqual(tempos(scaled),
                         [round(tempo / 0.75) for tempo in tempos(midi_data)])
        self.assertAlmostEqual(scaled.length, midi_data.length / 0.75, places=3)

    def test_tempo_map_shared_between_tracks_is_scaled_once(self):
        midi_data = midi_to_part_mp3s.ensure_midi_well_formatted(mido.MidiFile(FIXTURE))
        scaled = midi_to_part_mp3s.scale_tempo(midi_data, 0.5)
        self.assertAlmostEqual(scaled.length, 2 * midi_data.length, places=3)

    def test_original_is_not_changed(self):
        midi_data = mido.MidiFile(FIXTURE)
        original = tempos(midi_data)
        midi_to_part_mp3s.scale_tempo(midi_data, 0.5)
        self.assertEqual(tempos(midi_data), original)

    def test_midi_without_tempo_events_gets_slower_default_tempo(self):
        midi_data = mido.MidiFile()
        track = mido.MidiTrack()
        track.append(mido.Message('note_on', note=60, time=0))
        track.append(mido.Message('note_off', note=60, time=midi_data.ticks_per_beat))
        midi_data.tracks.append(track)
        scaled = midi_to_part_mp3s.scale_tempo(midi_data, 0.5)
        self.assertEqual(tempos(scaled), [1000000])
        self.assertAlmostEqual(scaled.length, 2 * midi_data.length)


class TestSlowTempoArgument(unittest.TestCase):
    def parse(self, arguments):
        return midi_to_part_mp3s.get_parser().parse_args(['-f', 'my_midi.mid'] + arguments)

    def test_default_is_no_slow_version(self):
        self.assertEqual(self.parse([]).slow_tempo, [])

    def test_several_tempos(self):
        self.assertEqual(self.parse(['--slow-tempo', '75', '50']).slow_tempo, [75, 50])

    def test_out_of_range_is_rejected(self):
        for value in ['100', '5', 'slow']:
            with self.assertRaises(SystemExit):
                self.parse(['--slow-tempo', value])


class TestSlowVersions(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(OUTPUT, ignore_errors=True)
        self.addCleanup(shutil.rmtree, OUTPUT, True)

    def test_slow_versions_are_created_in_addition(self):
        reports = []
        midi_to_part_mp3s.main(['-f', FIXTURE, '-o', OUTPUT, '--slow-tempo', '50'],
                               lambda done, total, seconds: reports.append((done, total)))
        files = set(os.listdir(OUTPUT))
        for name in ['all', 'soprano 1', 'soprano 1 with accompaniment']:
            self.assertIn(name + '.mp3', files)
            self.assertIn(name + ' (50% tempo).mp3', files)
        self.assertFalse(any(name.endswith('.midi') for name in files))
        normal = sox.file_info.duration(OUTPUT + '/soprano 1 with accompaniment.mp3')
        slow = sox.file_info.duration(OUTPUT + '/soprano 1 with accompaniment (50% tempo).mp3')
        # the piece takes twice as long, the reverb tail at the end stays the same
        piece_length = mido.MidiFile(FIXTURE).length
        self.assertAlmostEqual(slow - normal, piece_length, delta=0.2)
        # the progress counts the slow version twice, as it is twice as long
        self.assertAlmostEqual(reports[-1][0], reports[-1][1])
        halfway = [done for done, total in reports if done <= total / 3 + 1e-9]
        self.assertAlmostEqual(max(halfway), reports[-1][1] / 3)


if __name__ == '__main__':
    unittest.main()
