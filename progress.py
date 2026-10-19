"""Progress and remaining time of a midi-to-part-mp3s conversion"""

import threading
import time

# Rendering one part takes about this many seconds per second of audio. Only
# used until the first step is finished, after that the measured speed counts.
SECONDS_PER_AUDIO_SECOND = 0.025


class ProgressTracker:
    """Receives the progress reports of midi_to_part_mp3s and estimates the
    remaining time. It is passed as progress callback and called as
    tracker(done_units, total_units, audio_seconds) after every step.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._done = 0.0
        self._total = 0.0
        self._audio_seconds = 0.0
        self._started = None
        self._reported = None
        self._seconds_per_unit = None

    def __call__(self, done_units: float, total_units: float, audio_seconds: float) -> None:
        with self._lock:
            now = self._clock()
            if self._started is None:
                self._started = now
            self._done = done_units
            self._total = total_units
            self._audio_seconds = audio_seconds
            self._reported = now
            if done_units > 0:
                self._seconds_per_unit = (now - self._started) / done_units

    def snapshot(self) -> dict:
        """Returns the percentage done and the estimated remaining seconds,
        which are None as long as nothing has been reported."""
        with self._lock:
            if self._started is None or self._total <= 0:
                return {"percent": 0, "remaining_s": None}
            now = self._clock()
            if self._seconds_per_unit is None:
                # nothing finished yet: estimate from the length of the piece
                expected = self._total * self._audio_seconds * SECONDS_PER_AUDIO_SECOND
                remaining = expected - (now - self._started)
            else:
                # count down from the estimate made at the last report
                remaining = (self._total - self._done) * self._seconds_per_unit \
                    - (now - self._reported)
            # the units are fractions, allow for rounding errors in their sum
            finished = self._done >= self._total * 0.9999
            return {
                "percent": round(100 * self._done / self._total),
                "remaining_s": 0 if finished else max(1, round(remaining)),
            }
