# Midi to Part MP3s

This program takes a midi or MusicXML file that contains every part of a choral work (e.g. SATB)
and generates practice MP3 tracks for each voice. In every practice track the practised voice is
clearly louder than all other parts.

It can be used in two ways:

* as a **web app** in the browser (easiest with Docker, see [Running with Docker](#running-with-docker))
* as a **command line program** (see [Command line usage](#command-line-usage))

## Generated files

For every voice (e.g. `soprano 1`) the following files are generated:

* `soprano 1.mp3` – the voice on its own
* `soprano 1 with accompaniment.mp3` – the voice together with all other parts, the voice
  itself is louder than the rest
* `all.mp3` – all parts equally loud
* `accompaniment.mp3` – the instrumental accompaniment on its own, if tracks were assigned to it
  (e.g. piano or orchestra). It plays along in all other files, but gets no practice track of its own.

Optionally the following can be added:

* **Slower versions:** every file is also created at a slower tempo, e.g.
  `soprano 1 with accompaniment (75% tempo).mp3`. The pitch stays the same.
* **Count-in:** all files start with one bar of clicks. If the piece starts with a pickup bar,
  the count-in is based on the next full bar.
* **Click:** a quiet click on every beat throughout the piece.

How the volumes of the practised voice and the other parts are calculated is explained in
[docs/voice-loudness.md](docs/voice-loudness.md).

## Web app

1. Select a midi or MusicXML file (`.mid`, `.midi`, `.mxl`, `.musicxml`, `.xml`) or drop it
   onto the page. A spinner is shown while the score is read.
2. The score and its midi tracks are displayed. Drag each track onto the voice it belongs to
   (Soprano, Alto, Tenor, Bass). Several tracks per voice are possible, e.g. for SSAATTBB.
   Drag piano, organ or orchestra tracks onto "Accompaniment" (the "i" button next to it explains
   the lane). Tracks left in "Midi Tracks" are not included in any file.
3. Optionally choose an instrument that is used for all voices instead of the default ones, a
   slower version (90, 75, 60 or 50 % tempo), a one bar count-in and a quiet click throughout.
4. Use the sliders to set how many dB the practised voice is louder than the rest (0 to 20 dB,
   default 8 dB) and, if tracks were assigned to "Accompaniment", how loud the accompaniment is
   compared to each other voice (-12 to +12 dB, default +6 dB).
5. Click "Create part mp3s and download". A progress bar shows how far the conversion is and
   approximately how long it will still take. When it is finished, a zip file with all mp3s is
   downloaded.

## Running with Docker

A pre-built Docker image is published to the GitHub Container Registry. This is the
easiest way to run the web app — no need to install Python, Fluidsynth, Lame, or SoX
on your machine.

#### Docker

Pull and run the image, publishing the container's port 8080 to a local port of your
choice (e.g. 4000):

```bash
docker run -p 4000:8080 ghcr.io/oli-ver/midi-to-part-mp3s
```

Open <http://127.0.0.1:4000> in a browser.

The container runs as an unprivileged user and listens on port 8080. Hosting platforms that
set the `PORT` environment variable (e.g. Render or Fly.io) are supported, the app then
listens on `$PORT` instead.

#### Docker Compose

The repository includes a `docker-compose.yml` that uses the published image and
exposes port 4000:

```bash
docker compose up
```

Open <http://127.0.0.1:4000> in a browser. Adjust the port mapping in
`docker-compose.yml` if you need a different local port.

#### Building the image locally

If you prefer to build the image yourself instead of pulling the pre-built one:

```bash
docker build --tag=midi-to-part-mp3 .
docker run -p 4000:8080 midi-to-part-mp3
```

Or use the docker compose dev configuration, which builds the image from your working copy:

```bash
docker compose -f docker-compose-dev.yml build
docker compose -f docker-compose-dev.yml up
```

The build downloads the [Timbres of Heaven](http://midkar.com/soundfonts/) soundfont and
checks its SHA-256 checksum, so no soundfont needs to be present in the working copy.

#### Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `PORT` | `8080` | Port the web app listens on inside the container |
| `MAX_PARALLEL_JOBS` | `2` | Number of conversions that run at the same time, further ones wait in a queue |

The web app runs in a single gunicorn worker process with several threads, because the
progress of running conversions is kept in memory. Finished zip files can be downloaded for
15 minutes.

## Installation without Docker

```bash
git clone https://github.com/oli-ver/midi-to-part-mp3s
cd midi-to-part-mp3s
# Debian/Ubuntu
sudo apt-get install fluidsynth lame sox libsox-fmt-mp3
# macOS
brew install fluid-synth lame sox
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then place a soundfont at `./soundfonts/timbres-of-heaven.sf2` (see below).

### Dependencies

* Python 3 (the Docker image uses Python 3.14)
* [Fluidsynth](http://www.fluidsynth.org/) - MIDI-to-WAVE converter and player.
* [Lame](http://lame.sourceforge.net/) - create mp3 files.
* [SoX](http://sox.sourceforge.net/) - mix audio files, including its mp3 support (`libsox-fmt-mp3` on Debian/Ubuntu).
* [mido](https://mido.readthedocs.io/en/latest/)  - midi objects for python.
* [music21](https://web.mit.edu/music21/) - music toolkit used to convert MusicXML to midi.
* [NumPy](https://numpy.org/) - calculates the balance between the practised voice and the other parts.
* A general soundfont. This must be placed within './soundfonts'. The program assumes you have
  [Timbres of Heaven](http://midkar.com/soundfonts/) downloaded to that folder and named
  `timbres-of-heaven.sf2`. The `Dockerfile` shows where to download it. Any other General MIDI
  soundfont (e.g. FluidR3_GM) works as well if it is saved under this name. If you download an
  `.sfark` file, you can [go here to convert it](https://cloudconvert.com/sfark-to-sf2) to ".sf2".

## Command line usage

**Tempo map:** Midi track 0 usually holds the tempo and time signatures (the tempo map). It is
added to every voice automatically, otherwise a 5 minute piece might be over in 1 minute. If
track 0 also contains notes, the tempo map is split off into a separate track first.

### Quick start

By default, tracks 1-4 are assigned to SATB respectively:

`$ ./midi-to-part-mp3s -f ~/Downloads/my-midi.mid`

The mp3 files will appear in the folder `./output`.

### Detailed

To customize which input tracks are assigned to which voices and certain volume ratios.

```
usage: midi-to-part-mp3s [-h] [-s SOPRANO] [-a ALTO] [-t TENOR] [-b BASS]
                         [-in INSTRUMENT] [-iv INSTRUMENTAL_VOLUME] [-m VOICE_MARGIN]
                         [-i INSTRUMENTAL_ACCOMPANIMENT [INSTRUMENTAL_ACCOMPANIMENT ...]]
                         [-st SLOW_TEMPO [SLOW_TEMPO ...]] [-ci] [-cl] [-o OUTPUT]
                         -f FILE_PATH

options:
  -h, --help            show this help message and exit
  -s, --soprano SOPRANO
                        comma separated list of midi track IDs, defaults to "1"
  -a, --alto ALTO       comma separated list of midi track IDs, defaults to "2"
  -t, --tenor TENOR     comma separated list of midi track IDs, defaults to "3"
  -b, --bass BASS       comma separated list of midi track IDs, defaults to "4"
  -in, --instrument INSTRUMENT
                        instrument that should be used for all voices instead of the
                        advice given at cpdl.org
  -iv, --instrumental-volume INSTRUMENTAL_VOLUME
                        loudness of the instrumental accompaniment relative to each
                        other voice, defaults to 2.0
  -m, --voice-margin VOICE_MARGIN
                        how many dB the practised voice is louder than all other parts
                        together, defaults to 8.0
  -i, --instrumental-accompaniment INSTRUMENTAL_ACCOMPANIMENT [INSTRUMENTAL_ACCOMPANIMENT ...]
                        midi tracks that appear in all accompaniment mp3s e.g. piano or
                        orchestra
  -st, --slow-tempo SLOW_TEMPO [SLOW_TEMPO ...]
                        additionally create all files at these percentages of the
                        original tempo, e.g. "75" or "75 50". The pitch stays the same
  -ci, --count-in       start all files with one bar of clicks to count in
  -cl, --click          add a quiet click on every beat throughout the piece
  -o, --output OUTPUT   Output folder for the files. Defaults to './output'

mandatory argument:
  -f, --file-path FILE_PATH
                        Input file to generate the tracks from. Can be Midi or MusicXML
                        (.mid, .midi, .mxl, .musicxml)
```

Several tracks for one voice create several practice tracks, e.g.
`-s 1,2 -a 3,4` generates `soprano 1`, `soprano 2`, `alto 1` and `alto 2`.

With `--slow-tempo 75` every file is also created at 75 % of the original tempo, e.g.
`soprano 1 with accompaniment (75% tempo).mp3`. The web app offers the same as "Also create a
slower version".

`-i` takes the midi tracks of the instrumental accompaniment. Unlike in the web app, track 0
(the tempo map) is not added to them automatically, so include it, e.g. `-i 0 5`.

## Development

### Virtual Env

When developing, you probably want the python requirements to be installed in a virtual env. We
assume you name this `mtp_venv`.

```bash
$ python3 -m venv mtp_venv
$ source mtp_venv/bin/activate
(mtp_venv) $ pip install -r requirements.txt
```

### Static type checker

First install [mypy](http://mypy-lang.org/) `$ pip3 install mypy`.  Now run `$
mypy midi_to_part_mp3s.py`. Or better yet, integrate `mypy` to your editor for inline
type warnings.

### Code formatting

First install [autopep8](https://pypi.org/project/autopep8/) `$ pip3 install autopep8`. Now run
`$ autopep8 <filename>`. Best include `autopep8` in your editor to format the code on save automatically.

### Tests

Assuming you use the virtual env run all unit tests by calling the following command:

```bash
(mtp_venv) $ python -m unittest discover -s tests/ -p 'test*.py'
```

The integration tests call Fluidsynth, Lame and SoX and need the soundfont in `./soundfonts`.
To run the tests without installing anything locally, build the `test` stage of the Docker
image. This is also what the CI does for every pull request:

```bash
docker build --target test --tag midi-to-part-mp3-test .
docker run --rm midi-to-part-mp3-test
```

### Available fixtures

* tests/fixtures/Schumann-op67-4.mid – already includes a separate tempo map. Happy case.
* tests/fixtures/Schubert-872-sanctus.mid – does not have a separate tempo map, therefore exercises our internal midi rewrite features
* tests/fixtures/Brahms-Da-unten-im-Tale.mid - Another SATB example for general testing
* tests/fixtures/Abendlied-Rheinberger.xml - MusicXML example to test conversion and SSAATTBB track generation

### Web App Development

The web app serves its front-end libraries (jQuery, Bootstrap, opensheetmusicdisplay)
from `webapp/static/vendor/`, which is generated from npm dependencies and not checked
into the repo. Install them once (or after `package.json` changes) before running
locally:

```bash
$ cd webapp
$ npm install   # also runs "npm run build", which copies vendor files into static/vendor
```

Start the application in development mode (will reload automatically on code changes):
`$ FLASK_APP=webapp/app.py FLASK_DEBUG=1 flask run`

Open the url <http://127.0.0.1:5000/> in a browser. Code changes will be reloaded automatically.

The conversion runs as a background job: `POST /jobs` starts it and returns a job id,
`GET /jobs/<id>` returns the progress and the estimated remaining time, and
`GET /jobs/<id>/download` returns the zip file once the job is finished.
