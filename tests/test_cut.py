"""Tests for vodmoments.cut — actually cutting clips with ffmpeg."""

import math
import os
import random
import struct
import tempfile
import unittest
import wave

from vodmoments.cut import CutError, cut_clips
from vodmoments.score import Moment

SAMPLE_RATE = 16000


def _write_wav(path: str, samples: list[float]) -> None:
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples
        )
        wav.writeframes(frames)


def _seconds_of(value_fn, seconds: float) -> list[float]:
    return [value_fn(i / SAMPLE_RATE) for i in range(int(seconds * SAMPLE_RATE))]


def _burst_wav(seconds: float = 60.0, burst_at: float = 20.0) -> str:
    """A 60s silent WAV with a 2s loud burst at ``burst_at``."""
    rng = random.Random(5)
    samples = _seconds_of(lambda t: 0.0, seconds)
    burst = [
        rng.uniform(-0.9, 0.9) * math.exp(-5.0 * (i / SAMPLE_RATE))
        for i in range(2 * SAMPLE_RATE)
    ]
    start = int(burst_at * SAMPLE_RATE)
    samples[start:start + 2 * SAMPLE_RATE] = burst
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    _write_wav(tmp.name, samples)
    tmp.close()
    return tmp.name


def _moment(start: float, end: float) -> Moment:
    return Moment(start=start, end=end, score=80, reasons=["test"],
                  quote="", source="audio")


class TestCutClips(unittest.TestCase):
    def test_cut_makes_a_real_file(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                results = cut_clips([_moment(5.0, 25.0)], media, out_dir)
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0].ok, results[0].error)
                self.assertTrue(os.path.isfile(results[0].path))
                self.assertEqual(results[0].moment.clip, results[0].path)
                self.assertTrue(results[0].path.endswith(".wav"))  # keeps the input type
                with wave.open(results[0].path, "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                self.assertAlmostEqual(duration, 20.0, delta=0.1)
        finally:
            os.unlink(media)

    def test_cut_content_matches_the_slice(self):
        # The burst at 20s must be inside the cut clip, silence before it.
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                results = cut_clips([_moment(15.0, 25.0)], media, out_dir)
                self.assertTrue(results[0].ok, results[0].error)
                with wave.open(results[0].path, "rb") as wav:
                    frames = wav.readframes(wav.getnframes())
                samples = struct.unpack(f"<{len(frames) // 2}h", frames)
                # Burst sits 5s into a 10s clip: silence in the first 4s,
                # loud in the 5–7s window.
                early = max(abs(s) for s in samples[:4 * SAMPLE_RATE])
                burst_window = max(abs(s) for s in samples[5 * SAMPLE_RATE:7 * SAMPLE_RATE])
                self.assertLess(early, 100)  # silence
                self.assertGreater(burst_window, 10000)  # the burst
        finally:
            os.unlink(media)

    def test_same_start_gets_unique_names(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                results = cut_clips(
                    [_moment(5.0, 15.0), _moment(5.0, 12.0)], media, out_dir
                )
            paths = {r.path for r in results}
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(r.ok for r in results))
            names = sorted(os.path.basename(p) for p in paths)
            self.assertIn("clip-000005.wav", names)
            self.assertIn("clip-000005-2.wav", names)
        finally:
            os.unlink(media)

    def test_empty_moments_cut_nothing(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                self.assertEqual(cut_clips([], media, out_dir), [])
                self.assertEqual(os.listdir(out_dir), [])
        finally:
            os.unlink(media)

    def test_missing_media_raises(self):
        with tempfile.TemporaryDirectory() as out_dir:
            with self.assertRaises(CutError):
                cut_clips([_moment(0.0, 10.0)], "/tmp/does-not-exist-vod-moments.mp4", out_dir)

    def test_zero_length_moment_is_a_failed_result(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                results = cut_clips([_moment(10.0, 10.0)], media, out_dir)
            self.assertFalse(results[0].ok)
            self.assertIn("no length", results[0].error)
        finally:
            os.unlink(media)


if __name__ == "__main__":
    unittest.main()
