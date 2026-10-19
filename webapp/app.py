"""Web app for midi-to-part-mp3s"""

import argparse
import io
import os
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from zipfile import ZipFile
import uuid
import shutil
from typing import Dict, List
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
from progress import ProgressTracker # pylint: disable=C0413
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
ACCOMPANIMENT: str = "accompaniment"
VOICE_MARGIN: str = "voice_margin"
ACCOMPANIMENT_VOLUME: str = "accompaniment_volume"
SLOW_TEMPO: str = "slow_tempo"
COUNT_IN: str = "count_in"
CLICK: str = "click"
MUSICXML: str = "musicxml"
OUTPUT: str = "output"

TEMP_FOLDER: str = "tmp"
OUTPUT_FOLDER: str = "out"
FILENAME: str = "part-mp3s.zip"
ALLOWED_EXTENSIONS = (".mid", ".midi", ".mxl", ".musicxml", ".xml")
# allowed slider values in dB, see docs/voice-loudness.md
VOICE_MARGIN_RANGE_DECIBEL = (0.0, 20.0)
ACCOMPANIMENT_VOLUME_RANGE_DECIBEL = (-12.0, 12.0)
# conversions running at the same time, further jobs wait in a queue
MAX_PARALLEL_JOBS = int(os.environ.get("MAX_PARALLEL_JOBS", "2"))
# finished jobs are deleted after this many seconds, even if never downloaded
JOB_RETENTION_S = 15 * 60


class Job:
    """A conversion running in the background"""

    def __init__(self, folder: str):
        self.folder = folder
        self.status = "queued"
        self.progress = ProgressTracker()
        self.zip_path = None
        self.finished = None


jobs: Dict[str, Job] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS)


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
    try:
        output_folder, argument_list = _arguments_from_form(random_folder_name)
        app.logger.info("Starting midi_to_part_mp3s with %s", argument_list)
        midi_to_part_mp3s.main(argument_list)
        return _send_zip_file(output_folder)
    finally:
        shutil.rmtree(random_folder_name, ignore_errors=True)


@app.route("/jobs", methods=["POST"])
def create_job():
    """Start generating the mp3s in the background and return the job id"""

    _remove_expired_jobs()
    random_folder_name = _check_tmp_folder()
    try:
        output_folder, argument_list = _arguments_from_form(random_folder_name)
    except Exception:
        shutil.rmtree(random_folder_name, ignore_errors=True)
        raise
    job_id = os.path.basename(random_folder_name)
    job = Job(random_folder_name)
    with jobs_lock:
        jobs[job_id] = job
    app.logger.info("Queueing job %s with %s", job_id, argument_list)
    executor.submit(_run_job, job, output_folder, argument_list)
    return {"id": job_id}, 202


@app.route("/jobs/<job_id>")
def job_status(job_id: str):
    """Return the state, the percentage done and the estimated remaining seconds"""

    job = _get_job(job_id)
    return {"status": job.status, **job.progress.snapshot()}


@app.route("/jobs/<job_id>/download")
def job_download(job_id: str):
    """Send the zip file of a finished job"""

    job = _get_job(job_id)
    if job.status != "done":
        abort(409, "The job is not finished")
    return send_file(job.zip_path, mimetype="application/zip",
                     download_name=FILENAME, as_attachment=True)


def _run_job(job: Job, output_folder: str, argument_list: List[str]) -> None:
    job.status = "running"
    try:
        midi_to_part_mp3s.main(argument_list, job.progress)
        # absolute, as send_file resolves relative paths against the app folder
        zip_path = os.path.abspath(f"{job.folder}/{FILENAME}")
        _write_zip_file(output_folder, zip_path)
        shutil.rmtree(output_folder, ignore_errors=True)
        job.zip_path = zip_path
        job.status = "done"
    except Exception:  # pylint: disable=W0718
        app.logger.exception("Job in %s failed", job.folder)
        shutil.rmtree(job.folder, ignore_errors=True)
        job.status = "failed"
    job.finished = time.monotonic()


def _get_job(job_id: str) -> Job:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        abort(404, "Unknown job")
    return job


def _remove_expired_jobs() -> None:
    now = time.monotonic()
    with jobs_lock:
        expired = [job_id for job_id, job in jobs.items()
                   if job.finished and now - job.finished > JOB_RETENTION_S]
        for job_id in expired:
            shutil.rmtree(jobs.pop(job_id).folder, ignore_errors=True)


def _arguments_from_form(random_folder_name: str):
    music_xml = request.form.get(MUSICXML)
    if not music_xml:
        abort(400, "No MusicXML data received")
    midi_file_path = _save_musicxml_file(random_folder_name, music_xml)
    return _create_argument_list(
        midi_file_path,
        request.form.getlist(SOPRANO),
        request.form.getlist(ALTO),
        request.form.getlist(TENOR),
        request.form.getlist(BASS),
        request.form.get(INSTRUMENT),
        random_folder_name,
        request.form.getlist(ACCOMPANIMENT),
        _decibel_from_form(VOICE_MARGIN, VOICE_MARGIN_RANGE_DECIBEL),
        _decibel_from_form(ACCOMPANIMENT_VOLUME, ACCOMPANIMENT_VOLUME_RANGE_DECIBEL),
        _slow_tempo_from_form(),
        _flag_from_form(COUNT_IN),
        _flag_from_form(CLICK),
    )


def _decibel_from_form(parameter: str, allowed_range):
    """Returns the decibel value of a slider, or None if it was not sent"""
    value = request.form.get(parameter)
    if not value:
        return None
    try:
        decibel_value = float(value)
    except ValueError:
        abort(400, f"{parameter} must be a number")
    if not allowed_range[0] <= decibel_value <= allowed_range[1]:
        abort(400, f"{parameter} must be between {allowed_range[0]} and {allowed_range[1]} dB")
    return decibel_value


def _slow_tempo_from_form():
    """Returns the percentage of the slower version, or None if none is wanted"""
    value = request.form.get(SLOW_TEMPO)
    if not value:
        return None
    try:
        return midi_to_part_mp3s.slow_tempo_percent(value)
    except argparse.ArgumentTypeError as error:
        abort(400, f"{SLOW_TEMPO}: {error}")


def _flag_from_form(name: str) -> bool:
    """Whether a checkbox was ticked, sent as "1" by the web app"""
    return request.form.get(name) in ("1", "on", "true")


def _create_argument_list(
    midi_file_path: str,
    soprano_tracks,
    alto_tracks,
    tenor_tracks,
    bass_tracks,
    instrument_id,
    random_folder_name,
    accompaniment_tracks=None,
    voice_margin_decibel=None,
    accompaniment_volume_decibel=None,
    slow_tempo=None,
    count_in=False,
    click=False,
) -> List[str]:
    argument_list: List[str] = ["-f", midi_file_path]
    _list_append_track_id(argument_list, SOPRANO, soprano_tracks)
    _list_append_track_id(argument_list, ALTO, alto_tracks)
    _list_append_track_id(argument_list, TENOR, tenor_tracks)
    _list_append_track_id(argument_list, BASS, bass_tracks)
    _single_append_argument(argument_list, INSTRUMENT, instrument_id)
    if accompaniment_tracks:
        # the accompaniment needs the tempo map (track 0) like the voices do
        argument_list.append("--instrumental-accompaniment")
        argument_list.append("0")
        argument_list.extend(str(int(track_id) + 1) for track_id in accompaniment_tracks)
    if voice_margin_decibel is not None:
        argument_list.extend(["--voice-margin", str(voice_margin_decibel)])
    if accompaniment_volume_decibel is not None:
        # the slider is in dB, the command line expects an amplitude factor
        argument_list.extend(["--instrumental-volume",
                              str(midi_to_part_mp3s.decibel_to_amplitude(accompaniment_volume_decibel))])
    if slow_tempo:
        argument_list.extend(["--slow-tempo", str(slow_tempo)])
    if count_in:
        argument_list.append("--count-in")
    if click:
        argument_list.append("--click")

    output_folder = f"{random_folder_name}/{OUTPUT_FOLDER}"
    _single_append_argument(argument_list, OUTPUT, output_folder)
    return output_folder, argument_list


def _write_zip_file(output_folder: str, target) -> None:
    with ZipFile(target, "w") as myzip:
        for file_name in os.listdir(output_folder):
            myzip.write(os.path.join(output_folder, file_name), file_name)


def _send_zip_file(output_folder: str):
    # Build the zip in memory so the temporary folder can be removed right away
    zip_buffer = io.BytesIO()
    _write_zip_file(output_folder, zip_buffer)
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
