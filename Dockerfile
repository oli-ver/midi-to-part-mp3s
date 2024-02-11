# Use an official Python runtime as a parent image
FROM python:3.10.7-slim-buster as base

# Install fluidsynth and lame
RUN apt-get update
RUN apt-get install -y fluidsynth lame sox libsox-fmt-mp3 timidity libjpeg-dev zlib1g-dev wget p7zip

# Set the working directory to /app
WORKDIR /app

# Copy python requirements file to app/
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app/

# Add sound fonts
WORKDIR /app/soundfonts
RUN wget "https://musescore.jeetee.net/rawfiles/Timbres%20of%20Heaven%20(XGM)%204.00(G).7z" -O timbres-of-heaven.7z
RUN p7zip -d timbres-of-heaven.7z
RUN mv "Timbres of Heaven (XGM) 4.00(G).sf2" "timbres-of-heaven.sf2"
RUN rm -f *.txt *.7z
WORKDIR /app

# Free up some space
RUN apt-get remove -y wget p7zip
RUN apt-get clean


FROM base as test
CMD ["python", "-m", "unittest", "discover", "-s", "tests/", "-p" ,"test*.py"]

FROM base as production

# Make port 80 available to the world outside this container
EXPOSE 80
# Run app.py when the container launches
CMD ["python", "webapp/app.py"]
