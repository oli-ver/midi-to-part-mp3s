import math
import os
import shutil
import subprocess
import tempfile
import unittest

# allow to import modules from parent dir (https://stackoverflow.com/a/33532002/2641951)
from inspect import getsourcefile
import os.path as path
import sys
current_dir = path.dirname(path.abspath(getsourcefile(lambda: 0)))
sys.path.insert(0, current_dir[:current_dir.rfind(path.sep)])
import midi_to_part_mp3s  # noqa: E402


class FakePart:
    def __init__(self, name, rms_db, peak_db=-6.0):
        self.name = name
        self.rms_db = rms_db
        self.peak_db = peak_db


def effective_power(part, gain):
    """Power of a part in the mix: its gain times its own measured level"""
    if part.rms_db is None:
        return 0.0
    return (gain * 10 ** (part.rms_db / 20)) ** 2


def own_vs_rest_db(own, parts, gains):
    own_power = effective_power(own, gains[parts.index(own)])
    rest_power = sum(effective_power(part, gain)
                     for part, gain in zip(parts, gains) if part is not own)
    return 10 * math.log10(own_power / rest_power)


class TestVoiceLoudness(unittest.TestCase):

    def test_practised_voice_is_louder_by_margin_for_every_voice(self):
        # strongly differing levels, like flutes next to string ensembles
        parts = [FakePart('soprano 1', -35.0), FakePart('alto 1', -51.5),
                 FakePart('tenor 1', -40.0), FakePart('bass 1', -26.0)]
        for own in parts:
            gains = midi_to_part_mp3s.accompaniment_gains(own, parts, 8.0, 2.0)
            self.assertAlmostEqual(own_vs_rest_db(own, parts, gains), 8.0, places=3)

    def test_margin_does_not_depend_on_number_of_voices(self):
        parts = [FakePart('soprano {}'.format(i), -30.0 - i) for i in range(1, 9)]
        gains = midi_to_part_mp3s.accompaniment_gains(parts[3], parts, 6.0, 2.0)
        self.assertAlmostEqual(own_vs_rest_db(parts[3], parts, gains), 6.0, places=3)

    def test_instrumental_accompaniment_counts_into_the_rest(self):
        parts = [FakePart('soprano 1', -35.0), FakePart('alto 1', -45.0),
                 FakePart('accompaniment', -20.0)]
        gains = midi_to_part_mp3s.accompaniment_gains(parts[0], parts, 8.0, 2.0)
        self.assertAlmostEqual(own_vs_rest_db(parts[0], parts, gains), 8.0, places=3)
        # accompaniment is twice (6 dB) as loud as the other voice
        accompaniment_db = 10 * math.log10(effective_power(parts[2], gains[2]))
        alto_db = 10 * math.log10(effective_power(parts[1], gains[1]))
        self.assertAlmostEqual(accompaniment_db - alto_db, 20 * math.log10(2.0), places=3)

    def test_silent_parts_are_left_out(self):
        parts = [FakePart('soprano 1', -35.0), FakePart('alto 1', None, None),
                 FakePart('tenor 1', -40.0)]
        gains = midi_to_part_mp3s.accompaniment_gains(parts[0], parts, 8.0, 2.0)
        self.assertEqual(gains[1], 0.0)
        self.assertAlmostEqual(own_vs_rest_db(parts[0], parts, gains), 8.0, places=3)

    def test_measure_level_ignores_rests(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        tone_path = os.path.join(temp_dir, 'tone.wav')
        # 1 s tone, 3 s rest, 1 s tone with amplitude 0.5
        subprocess.run(['sox', '-n', '-r', '44100', '-c', '2', tone_path,
                        'synth', '1', 'sine', '440', 'vol', '0.5',
                        'pad', '0', '3', 'repeat', '1'], check=True)
        rms_db, peak_db = midi_to_part_mp3s.measure_level(tone_path)
        self.assertAlmostEqual(rms_db, 20 * math.log10(0.5 / math.sqrt(2)), delta=1.0)
        self.assertAlmostEqual(peak_db, 20 * math.log10(0.5), delta=0.5)


class TestVoiceLoudnessIntegration(unittest.TestCase):
    def setUp(self):
        self.output = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.output)

    def test_mixes_do_not_clip(self):
        midi_to_part_mp3s.main(['-f', './tests/fixtures/Brahms-Da-unten-im-Tale.mid',
                                '-o', self.output])
        for file_name in os.listdir(self.output):
            _, peak_db = midi_to_part_mp3s.measure_level(
                os.path.join(self.output, file_name))
            self.assertIsNotNone(peak_db, file_name)
            self.assertLess(peak_db, 0.0, file_name)


if __name__ == '__main__':
    unittest.main()
