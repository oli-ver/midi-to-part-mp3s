import unittest
import os
import shutil

import sox  # type: ignore

output_directory = "./output"


def audio_length(mp3_filepath):
    return sox.file_info.duration(mp3_filepath)


class TestIntegration(unittest.TestCase):
    def setUp(self):
        if(os.path.exists(output_directory)):
            shutil.rmtree(output_directory)

    def test_conversion_of_midi_with_separate_tempo_map(self):
        midi_file_path = "-f ./tests/fixtures/Schumann-op67-4.mid"
        cmd = "./midi-to-part-mp3s {}".format(midi_file_path)
        os.system(cmd)

        all_parts_mp3_output = "{}/all.mp3".format(output_directory)
        self.assertTrue(os.path.isfile(all_parts_mp3_output))

    def test_midi_without_separate_tempo_map(self):
        midi_file_path = "-f ./tests/fixtures/Brahms-Da-unten-im-Tale.mid"
        cmd = "./midi-to-part-mp3s {}".format(midi_file_path)
        os.system(cmd)

        audio_lengths = []
        for output_file in ['soprano 1', 'alto 1', 'bass 1', 'tenor 1']:
            audio_lengths.append(audio_length("{}/{}.mp3".format(output_directory,
                                                                 output_file, ".mp3")))

        self.assertSequenceEqual(audio_lengths, [audio_lengths[0]] * 4)


if __name__ == '__main__':
    unittest.main()
