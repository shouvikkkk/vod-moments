"""Tests for vodmoments.score — window scoring and moment ranking."""

import unittest

from vodmoments.parse import Segment
from vodmoments.score import find_transcript_moments, score_window


def _segs(*lines):
    """Build segments from (start, text) pairs, each 6 seconds long."""
    return [Segment(start, start + 6, text) for start, text in lines]


class TestScoreWindow(unittest.TestCase):
    def test_quiet_driving_scores_zero(self):
        score, reasons, spoiler = score_window(
            "driving down the highway nice sunset just cruising along"
        )
        self.assertEqual(score, 0)
        self.assertEqual(reasons, [])
        self.assertFalse(spoiler)

    def test_laugh_burst_scores_high(self):
        score, reasons, _ = score_window(
            "hahaha no way he tripped lol that was so funny hahaha"
        )
        self.assertGreaterEqual(score, 25)
        self.assertIn("lots of laughing", reasons)

    def test_wasted_crash_scores_high(self):
        score, reasons, _ = score_window(
            "oh no the cops are chasing me WASTED no no no what just happened"
        )
        self.assertGreaterEqual(score, 25)
        self.assertIn("shocked reaction", reasons)

    def test_hinglish_reaction_counts(self):
        score, reasons, _ = score_window(
            "arre yaar bhai hahaha pagal hai ye aadmi"
        )
        self.assertGreaterEqual(score, 25)
        self.assertIn("Hinglish reaction", reasons)

    def test_caps_shouting_counts(self):
        score, reasons, _ = score_window(
            "OH MY GOD HE FLEW OFF THE BRIDGE WHAT THE HELL"
        )
        self.assertGreaterEqual(score, 25)
        self.assertIn("shouting (ALL CAPS)", reasons)

    def test_spoiler_hint_flagged(self):
        _, reasons, spoiler = score_window(
            "hahaha and then the ending twist when she dies oh my god"
        )
        self.assertTrue(spoiler)
        self.assertIn("possible story moment — check before posting", reasons)

    def test_single_word_never_decides(self):
        score, _, _ = score_window("the chase was long and the cops were far away")
        self.assertLess(score, 25)


class TestFindMoments(unittest.TestCase):
    def test_finds_planted_moments_in_order(self):
        segments = _segs(
            (5, "driving down the highway nice sunset"),
            (65, "hahaha no way he tripped lol"),
            (71, "bhai hahaha pagal hai ye aadmi clip it"),
            (130, "just checking the map nothing happening"),
            (190, "oh no the cops are chasing me WASTED"),
            (196, "no no no what just happened the car flipped"),
            (250, "driving slowly now calm and quiet"),
        )
        moments = find_transcript_moments(segments, top=10)
        self.assertEqual(len(moments), 2)
        self.assertLess(moments[0].start, moments[1].start)
        # Windows step every 10s, so the winning window may start one step
        # earlier than the first cue; the moment keeps 5s of setup.
        self.assertTrue(40 <= moments[0].start <= 80)
        self.assertTrue(160 <= moments[1].start <= 210)
        for moment in moments:
            self.assertGreaterEqual(moment.score, 25)
            self.assertTrue(moment.quote)

    def test_min_gap_dedupes_same_laugh(self):
        segments = _segs(
            (65, "hahaha lol that was funny"),
            (75, "hahaha still laughing lol"),
            (85, "hahaha oh my god lol"),
            (200, "WASTED no no no the cops got me oh my god"),
        )
        moments = find_transcript_moments(segments, top=10, min_gap=60)
        starts = [m.start for m in moments]
        self.assertEqual(len(moments), 2)
        self.assertTrue(any(50 <= s <= 90 for s in starts))

    def test_top_limits_results(self):
        segments = _segs(
            (65, "hahaha lol that was insane clip it"),
            (200, "WASTED no no no the cops got me oh my god"),
            (350, "hahaha clip it lol no way"),
        )
        moments = find_transcript_moments(segments, top=1)
        self.assertEqual(len(moments), 1)

    def test_quiet_stream_has_no_moments(self):
        segments = _segs(
            (5, "driving down the highway"),
            (65, "nice sunset today"),
            (130, "checking the map"),
        )
        self.assertEqual(find_transcript_moments(segments), [])

    def test_empty_segments(self):
        self.assertEqual(find_transcript_moments([]), [])


if __name__ == "__main__":
    unittest.main()
