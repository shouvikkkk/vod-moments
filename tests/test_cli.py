"""Tests for vodmoments.cli — end-to-end runs on the demo transcript."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from vodmoments.cli import main

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "..", "examples", "gta6-stream.srt")


class TestCli(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_demo_finds_three_moments(self):
        code, out, _ = self._run(["find", DEMO])
        self.assertEqual(code, 0)
        self.assertIn("3 found", out)
        self.assertIn("00:55", out)  # laugh burst
        self.assertIn("03:15", out)  # WASTED crash
        self.assertIn("05:25", out)  # bridge moment

    def test_json_output_is_valid(self):
        code, out, _ = self._run(["find", DEMO, "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["moments"]), 3)
        moment = payload["moments"][0]
        self.assertIn("start_hms", moment)
        self.assertIn("score", moment)
        self.assertIn("reasons", moment)
        self.assertIn("signal", moment)

    def test_csv_output_has_header(self):
        code, out, _ = self._run(["find", DEMO, "--format", "csv"])
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertTrue(lines[0].startswith("start,end,score"))
        self.assertEqual(len(lines), 4)  # header + 3 moments

    def test_top_limits(self):
        code, out, _ = self._run(["find", DEMO, "--top", "1"])
        self.assertEqual(code, 0)
        self.assertIn("1 found", out)

    def test_quiet_transcript_exits_1(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False) as tmp:
            tmp.write(
                "1\n00:00:05,000 --> 00:00:11,000\ndriving down the highway\n\n"
                "2\n00:00:12,000 --> 00:00:18,000\nnice sunset today\n"
            )
            path = tmp.name
        try:
            code, _, err = self._run(["find", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)
        self.assertIn("No moments found", err)

    def test_missing_file_exits_2(self):
        code, _, err = self._run(["find", "/tmp/no-such-transcript.srt"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_garbage_transcript_exits_2(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            tmp.write("just some words with no timestamps at all\n")
            path = tmp.name
        try:
            code, _, err = self._run(["find", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 2)
        self.assertIn("no usable cues", err)

    def test_out_writes_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            out_path = tmp.name
        try:
            code, out, _ = self._run(["find", DEMO, "--out", out_path])
            self.assertEqual(code, 0)
            with open(out_path, encoding="utf-8") as handle:
                self.assertIn("3 found", handle.read())
        finally:
            os.unlink(out_path)


def _burst_wav() -> str:
    """A 40s silent WAV with a loud 2s burst at 20s (audio-only mode)."""
    import math
    import random
    import struct
    import wave
    sr = 16000
    rng = random.Random(9)
    samples = [0.0] * (40 * sr)
    burst = [
        rng.uniform(-0.9, 0.9) * math.exp(-5.0 * (i / sr))
        for i in range(2 * sr)
    ]
    samples[20 * sr:22 * sr] = burst
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples
        ))
    tmp.close()
    return tmp.name


class TestAudioOnlyAndCut(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_audio_only_needs_no_transcript(self):
        media = _burst_wav()
        try:
            code, out, _ = self._run(["find", "--audio", media])
        finally:
            os.unlink(media)
        self.assertEqual(code, 0)
        self.assertIn("1 found", out)
        self.assertIn(media, out)  # the media file is the source label

    def test_audio_only_quiet_file_exits_1(self):
        import struct
        import wave
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            with wave.open(tmp.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 16000 * 10)
            path = tmp.name
        try:
            code, _, err = self._run(["find", "--audio", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)
        self.assertIn("No moments found", err)

    def test_neither_transcript_nor_audio_exits_2(self):
        code, _, err = self._run(["find"])
        self.assertEqual(code, 2)
        self.assertIn("transcript", err)

    def test_cut_without_audio_exits_2(self):
        code, _, err = self._run(["find", DEMO, "--cut"])
        self.assertEqual(code, 2)
        self.assertIn("--cut needs --audio", err)

    def test_cut_makes_real_clips(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                clips = os.path.join(tmpdir, "clips")
                code, out, err = self._run(
                    ["find", "--audio", media, "--cut", clips]
                )
                self.assertEqual(code, 0)
                self.assertIn("Cut 1 clip(s)", err)
                self.assertIn("→", out)
                files = os.listdir(clips)
                self.assertEqual(len(files), 1)
                self.assertTrue(files[0].endswith(".wav"))
        finally:
            os.unlink(media)

    def test_cut_default_dir_is_clips(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cwd = os.getcwd()
                os.chdir(tmpdir)
                try:
                    code, out, err = self._run(["find", "--audio", media, "--cut"])
                finally:
                    os.chdir(cwd)
                self.assertEqual(code, 0)
                self.assertIn("Cut 1 clip(s) into clips/", err)
                self.assertEqual(len(os.listdir(os.path.join(tmpdir, "clips"))), 1)
        finally:
            os.unlink(media)

    def test_json_clip_field(self):
        media = _burst_wav()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                clips = os.path.join(tmpdir, "clips")
                code, out, _ = self._run(
                    ["find", "--audio", media, "--cut", clips, "--format", "json"]
                )
                payload = json.loads(out)
                self.assertEqual(code, 0)
                self.assertTrue(payload["moments"][0]["clip"].endswith(".wav"))
                self.assertEqual(payload["moments"][0]["signal"], "audio")
        finally:
            os.unlink(media)

    def test_json_clip_is_null_without_cut(self):
        code, out, _ = self._run(["find", DEMO, "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIsNone(payload["moments"][0]["clip"])


if __name__ == "__main__":
    unittest.main()
