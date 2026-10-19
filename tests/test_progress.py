import unittest

from progress import ProgressTracker, SECONDS_PER_AUDIO_SECOND


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class TestProgressTracker(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.tracker = ProgressTracker(clock=self.clock)

    def test_nothing_reported_yet(self):
        self.assertEqual(self.tracker.snapshot(),
                         {"percent": 0, "remaining_s": None})

    def test_first_estimate_uses_length_of_piece(self):
        self.tracker(0, 10, 120)
        expected = 10 * 120 * SECONDS_PER_AUDIO_SECOND
        self.assertEqual(self.tracker.snapshot(),
                         {"percent": 0, "remaining_s": round(expected)})
        self.clock.now += 5
        self.assertEqual(self.tracker.snapshot()["remaining_s"],
                         round(expected - 5))

    def test_estimate_follows_measured_speed(self):
        self.tracker(0, 10, 120)
        self.clock.now += 8
        # 2 of 10 units took 8 seconds, so 8 units take another 32 seconds
        self.tracker(2, 10, 120)
        self.assertEqual(self.tracker.snapshot(),
                         {"percent": 20, "remaining_s": 32})
        # counts down between the reports
        self.clock.now += 2
        self.assertEqual(self.tracker.snapshot()["remaining_s"], 30)

    def test_estimate_never_reaches_zero_before_the_end(self):
        self.tracker(0, 10, 120)
        self.clock.now += 1
        self.tracker(5, 10, 120)
        self.clock.now += 60
        self.assertEqual(self.tracker.snapshot()["remaining_s"], 1)

    def test_finished(self):
        self.tracker(0, 10, 120)
        self.clock.now += 3
        self.tracker(10, 10, 120)
        self.assertEqual(self.tracker.snapshot(),
                         {"percent": 100, "remaining_s": 0})


if __name__ == '__main__':
    unittest.main()
