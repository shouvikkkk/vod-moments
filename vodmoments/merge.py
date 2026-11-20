"""Combine transcript moments and audio moments into one ranked list.

The two signals catch different things: the transcript catches jokes,
reactions and shouted lines; the audio catches crashes, screams and
celebrations that happen while nobody is talking.  When both fire within
30 seconds of each other, that is the strongest evidence of all — the
moment gets a boost and one entry, not two.
"""

from __future__ import annotations

from .score import Moment

AGREE_WINDOW = 30.0  # seconds: transcript + audio moments this close agree
AGREE_BONUS = 10  # points added when both signals fire on one moment


def merge_moments(
    transcript: list[Moment],
    audio: list[Moment],
    top: int = 10,
) -> list[Moment]:
    """Merge two ranked lists, boosting moments both signals agree on."""
    merged: list[Moment] = list(transcript)
    used_audio: set[int] = set()
    for t in merged:
        for j, a in enumerate(audio):
            if j in used_audio:
                continue
            if abs(a.start - t.start) <= AGREE_WINDOW:
                t.score = min(100, t.score + AGREE_BONUS)
                t.reasons = sorted(set(t.reasons + a.reasons))
                t.source = "both"
                used_audio.add(j)
                break
    for j, a in enumerate(audio):
        if j not in used_audio:
            merged.append(a)
    merged.sort(key=lambda m: (-m.score, m.start))
    top_list = merged[:top]
    top_list.sort(key=lambda m: m.start)
    return top_list
