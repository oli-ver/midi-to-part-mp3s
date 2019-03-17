import mido
import sys
import os

def track_names(midi_data):
  return list(map(lambda track: track.name, midi_dat.tracks))

def isolate_tracks(midi_data, track_numbers, output_filename):
  new_file = mido.MidiFile()

  for track_number in track_numbers:
    new_file.tracks.append(midi_data.tracks[track_number])

  new_file_path = "./output/{}.midi".format(output_filename)
  new_file.save(new_file_path)

  return new_file_path

def convert_midi_to_mp3(midifile_path):
  file_name_without_extension = os.path.splitext(midifile_path)[0]
  os.system("timidity {} -Ow -o - | lame - {}.mp3".format(
    midifile_path, file_name_without_extension)
  )

def change_instrument(midi_data, program_number):
  for track in midi_data.tracks:
    for message in track:
      if message.type == 'program_change':
        message.program = program_number

def separate_tracks_into_mp3s(midi_data, description):
  for track_name, track_numbers in description.items():
    convert_midi_to_mp3(isolate_tracks(midi_data, track_numbers, track_name))


midifile_path = sys.argv[1:]

# TODO: Document this and make optional
description = {
  "soprano": [0,1,2],
  "alt": [0,1,3],
  "tenor": [0,1,4],
  "bass": [0,1,5]
}

midi_data = mido.MidiFile(midifile_path)

change_instrument(midi_data, 0)
separate_tracks_into_mp3s(midi_data, description)
