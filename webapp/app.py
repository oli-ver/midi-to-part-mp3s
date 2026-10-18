"""Web app for midi-to-part-mp3s"""

import io
import os
from zipfile import ZipFile
import uuid
import shutil
from typing import List
from inspect import getsourcefile
import json
from flask import Flask, abort, render_template, request, send_file
from music21 import stream, converter
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

# import from parent dir according to https://stackoverflow.com/a/9331002
current_dir = os.path.dirname(os.path.abspath(getsourcefile(lambda: 0)))
os.sys.path.insert(0, current_dir[: current_dir.rfind(os.path.sep)])
import midi_to_part_mp3s # pylint: disable=C0413
os.sys.path.pop(0)


app = Flask(__name__)
# Reject uploads larger than 20 MB (choir scores are far smaller)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

FILE: str = "file"
SOPRANO: str = "soprano"
ALTO: str = "alto"
TENOR: str = "tenor"
BASS: str = "bass"
INSTRUMENT: str = "instrument"
MUSICXML: str = "musicxml"
OUTPUT: str = "output"

TEMP_FOLDER: str = "tmp"
OUTPUT_FOLDER: str = "out"
FILENAME: str = "part-mp3s.zip"
ALLOWED_EXTENSIONS = (".mid", ".midi", ".mxl", ".musicxml", ".xml")


@app.route("/")
def index():
    """Render index.html"""
    return render_template("index.html")


@app.route("/midi-info", methods=["POST"])
def midi_info():
    """Convert midi to MusicXML"""

    random_folder_name = _check_tmp_folder()
    try:
        midi_file_name = _get_musicxml_file(random_folder_name)
        app.logger.info("Converting uploaded file %s", midi_file_name)
        score: stream.Score = converter.parse(midi_file_name)
        musicxml_filename = f"{random_folder_name}/score.musicxml"
        score.write(fp=musicxml_filename)
        xml_content = None
        with open(musicxml_filename, encoding="utf-8") as file_stream:
            xml_content = file_stream.read()
    finally:
        shutil.rmtree(random_folder_name, ignore_errors=True)
    response_dict = {}
    response_dict["musicxml"] = xml_content
    response_dict["parts"] = []
    part_stream = score.parts.stream()
    for part in part_stream:
        response_dict["parts"].append(part.id)
    return json.dumps(response_dict)


@app.route("/download", methods=["POST"])
def midi_to_mp3():
    """Generate mp3 from midi"""

    random_folder_name = _check_tmp_folder()
    soprano_tracks = request.form.getlist(SOPRANO)
    alto_tracks = request.form.getlist(ALTO)
    tenor_tracks = request.form.getlist(TENOR)
    bass_tracks = request.form.getlist(BASS)
    instrument_id = request.form.get(INSTRUMENT)
    music_xml = request.form.get(MUSICXML)
    if not music_xml:
        abort(400, "No MusicXML data received")
    try:
        midi_file_path = _save_musicxml_file(random_folder_name, music_xml)
        output_folder, argument_list = _create_argument_list(
            midi_file_path,
            soprano_tracks,
            alto_tracks,
            tenor_tracks,
            bass_tracks,
            instrument_id,
            random_folder_name,
        )
        app.logger.info("Starting midi_to_part_mp3s with %s", argument_list)
        midi_to_part_mp3s.main(argument_list)
        return _send_zip_file(output_folder)
    finally:
        shutil.rmtree(random_folder_name, ignore_errors=True)


def _create_argument_list(
    midi_file_path: str,
    soprano_tracks,
    alto_tracks,
    tenor_tracks,
    bass_tracks,
    instrument_id,
    random_folder_name,
) -> List[str]:
    argument_list: List[str] = ["-f", midi_file_path]
    _list_append_track_id(argument_list, SOPRANO, soprano_tracks)
    _list_append_track_id(argument_list, ALTO, alto_tracks)
    _list_append_track_id(argument_list, TENOR, tenor_tracks)
    _list_append_track_id(argument_list, BASS, bass_tracks)
    _single_append_argument(argument_list, INSTRUMENT, instrument_id)

    output_folder = f"{random_folder_name}/{OUTPUT_FOLDER}"
    _single_append_argument(argument_list, OUTPUT, output_folder)
    return output_folder, argument_list


def _send_zip_file(output_folder: str):
    # Build the zip in memory so the temporary folder can be removed right away
    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, "w") as myzip:
        for file_name in os.listdir(output_folder):
            myzip.write(os.path.join(output_folder, file_name), file_name)
    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        download_name=FILENAME,
        as_attachment=True,
        max_age=300,
    )


def _list_append_track_id(
    argument_list: List[str], parameter: str, track_id_list: List[str]
) -> None:
    if track_id_list:
        argument_list.append(f"--{parameter}")
        track_id_int = []
        for track_id in track_id_list:
            # need to advance ID by 1 (midi track will have tempo map at track 0)
            track_id_int.append(str(int(track_id) + 1))
        argument_list.append(",".join(track_id_int))


def _single_append_argument(
    argument_list: List[str], parameter: str, value: str
) -> None:
    if value:
        argument_list.append(f"--{parameter}")
        argument_list.append(value)


def _check_tmp_folder() -> str:
    # Only create this request's own folder; other requests may still be running
    random_folder_name = uuid.uuid4()
    tmp_folder = f"{TEMP_FOLDER}/{random_folder_name}"
    os.makedirs(tmp_folder)
    return tmp_folder


def _get_musicxml_file(temp_folder: str) -> str:
    midi_file: FileStorage = request.files.get(FILE)
    if midi_file is None:
        abort(400, "No file uploaded")
    # Never trust the client file name: it may contain path components like "../"
    file_name = secure_filename(midi_file.filename or "")
    if not file_name.lower().endswith(ALLOWED_EXTENSIONS):
        abort(400, "Only midi or MusicXML files are supported")
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
    music_xml_path = os.path.join(temp_folder, file_name)
    midi_file.save(music_xml_path)
    return music_xml_path


def _save_musicxml_file(temp_folder: str, music_xml: str) -> str:
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
    music_xml_path = os.path.join(temp_folder, "temp.musicxml")
    with open(music_xml_path, "w", encoding="utf-8") as file_stream:
        file_stream.write(music_xml)
    return music_xml_path


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
