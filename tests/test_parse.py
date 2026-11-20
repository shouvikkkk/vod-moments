"""Tests for vodmoments.parse — SRT, VTT and pasted transcripts."""

import unittest

from vodmoments.parse import ParseError, parse_paste, parse_srt, parse_transcript, parse_vtt

SRT_SAMPLE = """1
00:00:05,000 --> 00:00:11,000
hello chat we are driving

2
00:00:12,500 --> 00:00:18,000
[Music]
hahaha that was funny
"""

VTT_SAMPLE = """WEBVTT

00:00:05.000 --> 00:00:11.000 align:start
hello chat we are driving

00:00:12.500 --> 00:00:18.000
hahaha that was funny
"""

PASTE_SAMPLE = """0:05 hello chat we are driving
0:12 hahaha that was funny
0:20 just cruising along
"""


class TestSrt(unittest.TestCase):
    def test_basic(self):
        segments, skipped = parse_srt(SRT_SAMPLE)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start, 5.0)
        self.assertEqual(segments[0].end, 11.0)
        self.assertEqual(segments[0].text, "hello chat we are driving")
        self.assertEqual(skipped, 0)

    def test_bracket_noise_removed(self):
        segments, _ = parse_srt(SRT_SAMPLE)
        self.assertEqual(segments[1].text, "hahaha that was funny")

    def test_bad_block_skipped_not_fatal(self):
        segments, skipped = parse_srt(SRT_SAMPLE + "\n99\nno timing line here\n")
        self.assertEqual(len(segments), 2)
        self.assertEqual(skipped, 1)


class TestVtt(unittest.TestCase):
    def test_basic(self):
        segments, skipped = parse_vtt(VTT_SAMPLE)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start, 5.0)
        self.assertEqual(segments[1].text, "hahaha that was funny")
        self.assertEqual(skipped, 0)


class TestPaste(unittest.TestCase):
    def test_basic(self):
        segments, skipped = parse_paste(PASTE_SAMPLE)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].start, 5.0)
        self.assertEqual(segments[0].end, 12.0)  # runs until the next cue
        self.assertEqual(segments[2].text, "just cruising along")

    def test_wrapped_line_glued_on(self):
        segments, _ = parse_paste("0:05 first half\nsecond half here\n0:12 next cue\n")
        self.assertEqual(segments[0].text, "first half second half here")

    def test_leading_junk_skipped(self):
        segments, skipped = parse_paste("some header line\n0:05 hello\n")
        self.assertEqual(len(segments), 1)
        self.assertEqual(skipped, 1)


class TestAutoDetect(unittest.TestCase):
    def test_detects_srt(self):
        segments, _ = parse_transcript(SRT_SAMPLE, "stream.srt")
        self.assertEqual(len(segments), 2)

    def test_detects_vtt_by_header(self):
        segments, _ = parse_transcript(VTT_SAMPLE, "captions.txt")
        self.assertEqual(len(segments), 2)

    def test_detects_paste(self):
        segments, _ = parse_transcript(PASTE_SAMPLE, "transcript.txt")
        self.assertEqual(len(segments), 3)

    def test_empty_raises(self):
        with self.assertRaises(ParseError):
            parse_transcript("   \n  ", "empty.srt")

    def test_no_cues_raises(self):
        with self.assertRaises(ParseError):
            parse_transcript("just some words with no timestamps at all", "x.txt")


if __name__ == "__main__":
    unittest.main()
