"""Tests for vodmoments.merge — combining transcript + audio signals."""

import unittest

from vodmoments.merge import merge_moments
from vodmoments.score import Moment


def _moment(start, score, source):
    return Moment(start=start, end=start + 30, score=score,
                  reasons=[source], quote="", source=source)


class TestMerge(unittest.TestCase):
    def test_agreeing_moments_boost_and_combine(self):
        merged = merge_moments(
            [_moment(60, 70, "transcript")],
            [_moment(70, 60, "audio")],
            top=5,
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].score, 80)
        self.assertEqual(merged[0].source, "both")
        self.assertIn("transcript", merged[0].reasons)
        self.assertIn("audio", merged[0].reasons)

    def test_disagreeing_moments_both_kept(self):
        merged = merge_moments(
            [_moment(60, 70, "transcript")],
            [_moment(300, 60, "audio")],
            top=5,
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual({m.source for m in merged}, {"transcript", "audio"})

    def test_boost_capped_at_100(self):
        merged = merge_moments(
            [_moment(60, 95, "transcript")],
            [_moment(65, 90, "audio")],
            top=5,
        )
        self.assertEqual(merged[0].score, 100)

    def test_top_limits_and_sorts_by_time(self):
        merged = merge_moments(
            [_moment(300, 90, "transcript"), _moment(60, 70, "transcript")],
            [_moment(500, 80, "audio")],
            top=2,
        )
        self.assertEqual(len(merged), 2)
        self.assertLess(merged[0].start, merged[1].start)


if __name__ == "__main__":
    unittest.main()
