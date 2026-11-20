"""Tests for vodmoments.audio — spike detection on synthetic WAV files.

Synthetic audio, not real streams: a burst of noise in silence must be
found, a sustained loud tone (in-game radio) must NOT be flagged, and a
quiet file must yield no moments.
"""

import math
import os
import random
import struct
import tempfile
import unittest
import wave

from vodmoments.audio import AudioError, extract_wav, find_audio_moments, read_chunks

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


class TestReadChunks(unittest.TestCase):
    def test_chunk_count_and_times(self):
        samples = _seconds_of(lambda t: 0.0, 2.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            _write_wav(tmp.name, samples)
            try:
                chunks, duration = read_chunks(tmp.name)
            finally:
                os.unlink(tmp.name)
        self.assertEqual(len(chunks), 4)  # 2s / 0.5s chunks
        self.assertAlmostEqual(duration, 2.0)
        self.assertEqual(chunks[0].time, 0.0)
        self.assertAlmostEqual(chunks[0].rms, 0.0)


class TestFindAudioMoments(unittest.TestCase):
    def _run(self, samples, min_gap=60.0):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            _write_wav(tmp.name, samples)
            try:
                moments, duration = find_audio_moments(tmp.name, top=5, min_gap=min_gap)
            finally:
                os.unlink(tmp.name)
        return moments, duration

    def test_burst_in_silence_is_found(self):
        rng = random.Random(7)
        samples = _seconds_of(lambda t: 0.0, 30.0)
        # A 2-second loud burst at 10s (a crash / scream): sharp attack,
        # fast decay — high crest, unlike steady noise or radio.
        burst = [
            rng.uniform(-0.9, 0.9) * math.exp(-5.0 * (i / SAMPLE_RATE))
            for i in range(2 * SAMPLE_RATE)
        ]
        samples[10 * SAMPLE_RATE:12 * SAMPLE_RATE] = burst
        moments, duration = self._run(samples)
        self.assertAlmostEqual(duration, 30.0)
        self.assertEqual(len(moments), 1)
        # Clip starts 15s of setup before the burst, clamped at 0.
        self.assertLessEqual(moments[0].start, 10.0)
        self.assertGreaterEqual(moments[0].end, 12.0)
        self.assertIn("sudden loud spike in the audio", moments[0].reasons)

    def test_sustained_loud_tone_is_not_a_moment(self):
        # In-game radio: loud the whole time, no sudden rise, low crest.
        samples = _seconds_of(lambda t: 0.5 * math.sin(2 * math.pi * 440 * t), 30.0)
        moments, _ = self._run(samples)
        self.assertEqual(moments, [])

    def test_quiet_file_has_no_moments(self):
        samples = _seconds_of(lambda t: 0.001 * math.sin(2 * math.pi * 220 * t), 10.0)
        moments, _ = self._run(samples)
        self.assertEqual(moments, [])

    def test_two_bursts_two_moments(self):
        rng = random.Random(11)
        samples = _seconds_of(lambda t: 0.0, 60.0)
        for at in (10, 45):
            burst = [
                rng.uniform(-0.9, 0.9) * math.exp(-5.0 * (i / SAMPLE_RATE))
                for i in range(2 * SAMPLE_RATE)
            ]
            samples[at * SAMPLE_RATE:(at + 2) * SAMPLE_RATE] = burst
        moments, _ = self._run(samples, min_gap=20.0)
        self.assertEqual(len(moments), 2)

    def test_missing_file_raises(self):
        with self.assertRaises(AudioError):
            find_audio_moments("/tmp/does-not-exist-vod-moments.mp4")


class TestExtractWav(unittest.TestCase):
    def test_wav_input_round_trips(self):
        samples = _seconds_of(lambda t: 0.0, 1.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            _write_wav(tmp.name, samples)
            try:
                out = extract_wav(tmp.name)
                self.assertTrue(os.path.getsize(out) > 0)
                os.unlink(out)
            finally:
                os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
