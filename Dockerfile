# Use an official Node image to build frontend vendor files
FROM node:26-trixie-slim AS node-build
WORKDIR /build
# Copy the whole webapp directory so package.json, package-lock.json and scripts are available
COPY webapp ./webapp
# Install dependencies and run build (copy vendor files into webapp/static/vendor)
# Use npm ci when a lockfile is present for reproducible installs; fall back to npm install otherwise
RUN cd webapp && \
    if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi && \
    npm run build

# Use an official Python runtime as a parent image
FROM python:3.14-slim-trixie AS base

# Install fluidsynth and lame and other system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends fluidsynth lame sox libsox-fmt-mp3 timidity libjpeg-dev zlib1g-dev wget p7zip && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

# Copy python requirements file to app/
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Add sound fonts
WORKDIR /app/soundfonts
# Fail the build if the download fails or the archive is not the expected one
ARG SOUNDFONT_SHA256=e5cdfbfc85def9ee59dbd72bc17878dbd8a3a0a8159755fd594ad8b6c3ee4a9c
RUN wget "https://musescore.jeetee.net/rawfiles/Timbres%20of%20Heaven%20(XGM)%204.00(G).7z" -O timbres-of-heaven.7z && \
    echo "${SOUNDFONT_SHA256}  timbres-of-heaven.7z" | sha256sum -c - && \
    p7zip -d timbres-of-heaven.7z && \
    mv "Timbres of Heaven (XGM) 4.00(G).sf2" "timbres-of-heaven.sf2" && \
    rm -f *.txt *.7z

# Copy the current directory contents into the container at /app
COPY . /app/

# Copy built vendor files from node-build stage into the flask static folder
# This will place vendor files at /app/webapp/static/vendor/...
COPY --from=node-build /build/webapp/static/vendor /app/webapp/static/vendor

WORKDIR /app

# Free up some space
RUN apt-get remove -y wget p7zip && apt-get clean || true

FROM base AS test
CMD ["python", "-m", "unittest", "discover", "-s", "tests/", "-p" ,"test*.py"]

FROM base AS production

# Run as an unprivileged user that may only write the upload folder
RUN useradd --create-home --uid 10001 app && \
    mkdir -p /app/tmp && chown app:app /app/tmp
USER app

# Unprivileged users can't bind port 80, so listen on 8080 (or $PORT if the host sets it)
ENV PORT=8080
EXPOSE 8080
# One worker only: the job progress lives in memory, threads run requests in parallel
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --pythonpath webapp app:app"]
