"""Score windows of a transcript for clip-worthy moments.

The idea is simple: in a GTA stream the funny moments are the ones where
the streamer (and the game) suddenly get loud — laughing, shouting,
"WASTED", a chase, a crash.  We slide a 30-second window across the
transcript in 10-second steps, count the signals inside each window, and
rank the windows.  No model, no network, no account.

Signals are deliberately plain words, in English and in the Roman-script
Hinglish Indian creators actually speak on stream ("arre", "bhai", "pagal").
Auto-captions mis-hear words, so every signal is a small family of words
rather than one exact phrase, and a single word never decides a window on
its own — the score needs a cluster.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parse import Segment

WINDOW_SECONDS = 30.0
STEP_SECONDS = 10.0
MIN_SCORE = 25  # below this, a window is ordinary driving, not a moment
DEFAULT_MIN_GAP = 60.0  # seconds between two moments in the ranked list

# Laughing, in English and Roman-script Hinglish.  "ha" alone is too common
# to count; "haha"/"hahaha" and "lol"/"lmao" are the real signals.
LAUGH_WORDS = {
    "haha", "hahaha", "hahahaha", "hehe", "lol", "lmao", "lmfao", "rofl",
    "hah", "hihihi", "lolol",
}
# Shock / disbelief / "clip this" — the words people say right after the
# thing that makes the clip.
SHOCK_PHRASES = {
    "wasted", "busted", "oh my god", "omg", "no way", "what the",
    "clip it", "clip that", "no no no", "are you serious", "did you see that",
    "what just happened", "bro what", "oh no", "oh no no", "run run run",
    "he's dead", "she's dead", "i'm dead", "we're dead", "that was insane",
    "insane", "crazy", "unbelievable", "nooooo", "whyyyy",
}
# Things happening in the game that make a clip: chases, crashes, the law.
GTA_WORDS = {
    "cops", "police", "chase", "crash", "crashed", "wanted", "stars",
    "explosion", "exploded", "heist", "robbery", "mission failed",
    "ragdoll", "helicopter", "roadblock", "shootout", "gunfight",
    "car chase", "high speed", "near miss", "flipped", "blown up",
}
# Hinglish exclamations Indian creators actually use on stream.
HINGLISH_WORDS = {
    "arre", "arey", "oye", "bhai", "yaar", "pagal", "kya", "abe", "uff",
    "bhaiya", "arre yaar", "kya hua", "oh bhai", "bhai sahab",
}
# Words that hint a window contains a story beat, not just a funny moment.
# These only *flag* the moment ("possible story moment — check before
# posting"); they never hide it.
SPOILER_WORDS = {
    "ending", "dies", "died", "death", "betrayal", "betrayed", "twist",
    "final mission", "last mission", "sacrifice", "kills him", "kills her",
    "the ending", "story ends", "plot twist",
}

_ELONGATED_RE = re.compile(r"([a-z])\1{2,}", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-zA-Z]+")
_CAPS_RE = re.compile(r"\b[A-Z]{2,}\b")


@dataclass
class Moment:
    """One ranked, clip-worthy stretch of the stream."""

    start: float  # clip start (includes a few seconds of setup)
    end: float  # clip end (includes the payoff)
    score: int  # 0-100
    reasons: list[str] = field(default_factory=list)
    quote: str = ""  # the first line a viewer hears in the moment
    spoiler_hint: bool = False
    source: str = "transcript"  # "transcript" | "audio" | "both"


def _count_phrases(text: str, phrases: set[str]) -> int:
    lowered = " " + text.lower() + " "
    count = 0
    for phrase in phrases:
        if " " in phrase:
            count += lowered.count(" " + phrase + " ")
        else:
            count += len(re.findall(r"\b" + re.escape(phrase) + r"\b", lowered))
    return count


def _count_words(text: str, words: set[str]) -> int:
    found = set(_WORD_RE.findall(text.lower()))
    return len(found & words)


def _window_text(segments: list[Segment], start: float, end: float) -> str:
    parts = [seg.text for seg in segments if seg.start < end and seg.end > start]
    return " ".join(parts)


def score_window(text: str) -> tuple[int, list[str], bool]:
    """Score one window's text.  Returns (score 0-100, reasons, spoiler_hint)."""
    if not text.strip():
        return 0, [], False
    words = _WORD_RE.findall(text)
    word_count = max(len(words), 1)
    reasons: list[str] = []
    raw = 0.0

    laughs = _count_phrases(text, LAUGH_WORDS)
    if laughs:
        raw += min(laughs, 6) * 6
        reasons.append("lots of laughing" if laughs >= 3 else "laughing")

    shocks = _count_phrases(text, SHOCK_PHRASES)
    if shocks:
        raw += min(shocks, 4) * 8
        reasons.append("shocked reaction")

    gta = _count_words(text, GTA_WORDS) + _count_phrases(
        text, {p for p in GTA_WORDS if " " in p}
    )
    if gta:
        raw += min(gta, 5) * 4
        reasons.append("chase / crash / cops")

    hinglish = _count_words(text, HINGLISH_WORDS) + _count_phrases(
        text, {p for p in HINGLISH_WORDS if " " in p}
    )
    if hinglish:
        raw += min(hinglish, 4) * 5
        reasons.append("Hinglish reaction")

    caps = len(_CAPS_RE.findall(text))
    caps_ratio = caps / word_count
    if caps >= 3 and caps_ratio >= 0.08:
        raw += 10
        reasons.append("shouting (ALL CAPS)")

    exclaims = text.count("!")
    if exclaims >= 2:
        raw += min(exclaims, 5) * 3
        if "excited shouting" not in reasons:
            reasons.append("excited shouting")

    elongated = len(_ELONGATED_RE.findall(text))
    if elongated >= 2:
        raw += min(elongated, 4) * 3

    questions = text.count("?")
    if questions >= 3:
        raw += 4

    # A window that is all one long calm sentence is not a moment, however
    # many ordinary words it holds: require at least one real signal.
    if not reasons and raw < 12:
        return 0, [], False

    score = int(min(100, raw))
    spoiler_hint = bool(_count_phrases(text, SPOILER_WORDS))
    if spoiler_hint:
        reasons.append("possible story moment — check before posting")
    return score, reasons, spoiler_hint


def find_transcript_moments(
    segments: list[Segment],
    top: int = 10,
    min_gap: float = DEFAULT_MIN_GAP,
    min_score: int = MIN_SCORE,
) -> list[Moment]:
    """Rank the best moments in a transcript.

    Windows are 30 seconds long, stepped every 10 seconds.  The best window
    wins; any other window within ``min_gap`` seconds of a kept moment is
    dropped, so the list is moments, not the same laugh five times.
    """
    if not segments:
        return []
    duration = max(seg.end for seg in segments)
    candidates: list[Moment] = []
    start = 0.0
    while start < duration:
        end = start + WINDOW_SECONDS
        text = _window_text(segments, start, end)
        score, reasons, spoiler_hint = score_window(text)
        if score >= min_score:
            # The quote is the first captioned line inside the window.
            quote = next(
                (seg.text for seg in segments if seg.start < end and seg.end > start),
                "",
            )
            candidates.append(
                Moment(
                    start=max(0.0, start - 5),  # 5s of setup before the spike
                    end=min(duration, end + 5),  # 5s of payoff after it
                    score=score,
                    reasons=reasons,
                    quote=quote,
                    spoiler_hint=spoiler_hint,
                    source="transcript",
                )
            )
        start += STEP_SECONDS
    # Non-max suppression: best first, drop anything too close to a keeper.
    candidates.sort(key=lambda m: (-m.score, m.start))
    kept: list[Moment] = []
    for cand in candidates:
        if all(abs(cand.start - other.start) >= min_gap for other in kept):
            kept.append(cand)
        if len(kept) >= top:
            break
    kept.sort(key=lambda m: m.start)
    return kept
