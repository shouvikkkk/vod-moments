"""Tests for vodmoments.cli — end-to-end runs on the demo transcript."""

import io
import json
import os
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


if __name__ == "__main__":
    unittest.main()
