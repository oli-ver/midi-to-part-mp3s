# Use an official Node image to build frontend vendor files
FROM node:18-bullseye-slim as node-build
WORKDIR /build
# Copy package manifest and scripts
COPY webapp/package.json ./webapp/package.json
COPY webapp/scripts ./webapp/scripts
# Install dependencies and run build (copy vendor files into webapp/static/vendor)
RUN cd webapp && npm ci --silent && npm run build

# Use an official Python runtime as a parent image
FROM python:3.14-slim-trixie as base

# Install fluidsynth and lame and other system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends fluidsynth lame sox libsox-fmt-mp3 timidity libjpeg-dev zlib1g-dev wget p7zip && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

# Copy python requirements file to app/
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app/

# Copy built vendor files from node-build stage into the flask static folder
# This will place vendor files at /app/webapp/static/vendor/...
COPY --from=node-build /build/webapp/static/vendor /app/webapp/static/vendor

# Add sound fonts
WORKDIR /app/soundfonts
RUN wget "https://musescore.jeetee.net/rawfiles/Timbres%20of%20Heaven%20(XGM)%204.00(G).7z" -O timbres-of-heaven.7z && \
    p7zip -d timbres-of-heaven.7z && \
    mv "Timbres of Heaven (XGM) 4.00(G).sf2" "timbres-of-heaven.sf2" || true && \
    rm -f *.txt *.7z || true
WORKDIR /app

# Free up some space
RUN apt-get remove -y wget p7zip && apt-get clean || true

FROM base as test
CMD ["python", "-m", "unittest", "discover", "-s", "tests/", "-p" ,"test*.py"]

FROM base as production

# Make port 80 available to the world outside this container
EXPOSE 80
# Run app.py when the container launches
CMD ["python", "webapp/app.py"]
