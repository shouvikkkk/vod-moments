"""Parsers for stream transcripts and caption files.

vod-moments reads the words of a stream, not the video.  A transcript can
arrive in three shapes, and all three are common in the wild:

* ``.srt`` — SubRip, the format YouTube and Twitch caption downloads use.
* ``.vtt`` — WebVTT, the format YouTube's own caption export uses.
* A pasted transcript — the text you get from YouTube's "Show transcript"
  panel, one line per cue, each line starting with a timestamp like
  ``1:23`` or ``1:23:45``.

Auto-captions are messy: no punctuation, mis-heard words, ``[Music]`` and
``[Applause]`` markers, Hindi/Hinglish mixed with English.  The parsers
never crash on a bad line — they skip it, count it, and keep going.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """One captioned line: when it starts and ends, and what was said."""

    start: float  # seconds from the start of the stream
    end: float  # seconds from the start of the stream
    text: str


class ParseError(ValueError):
    """Raised when a file has no usable cues at all."""


# 00:01:23,456 (SRT) or 00:01:23.456 (VTT)
_TS_RE = re.compile(
    r"(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)
# Short paste timestamp: 1:23 (minutes:seconds) or 1:23:45 (hours:minutes:seconds).
_PASTE_TS_RE = re.compile(
    r"^(?P<a>\d+):(?P<b>\d{2})(?::(?P<c>\d{2}))?\s+(?P<text>.+)$"
)
# Stage directions from auto-captions: [Music], [Applause], [Laughter] ...
_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _to_seconds(hours: str, minutes: str, seconds: str, millis: str = "0") -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _clean(text: str) -> str:
    """Strip caption noise; keep the spoken words (any language)."""
    text = _BRACKET_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_srt(text: str) -> tuple[list[Segment], int]:
    """Parse SubRip text.  Returns (segments, skipped_lines)."""
    segments: list[Segment] = []
    skipped = 0
    # Cues are separated by blank lines.
    for block in re.split(r"\r?\n\r?\n", text.strip()):
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        # First line may be a cue number; the timing line holds "-->".
        timing_idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_idx is None:
            skipped += 1
            continue
        timing = lines[timing_idx]
        match = re.match(
            r"(?P<start>\d+:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
            r"(?P<end>\d+:\d{2}:\d{2}[,.]\d{3})",
            timing,
        )
        if match is None:
            skipped += 1
            continue
        start_m = _TS_RE.match(match.group("start"))
        end_m = _TS_RE.match(match.group("end"))
        if start_m is None or end_m is None:
            skipped += 1
            continue
        body = _clean(" ".join(lines[timing_idx + 1:]))
        if not body:
            skipped += 1
            continue
        segments.append(
            Segment(
                start=_to_seconds(*start_m.groups()),
                end=_to_seconds(*end_m.groups()),
                text=body,
            )
        )
    segments.sort(key=lambda seg: seg.start)
    return segments, skipped


def parse_vtt(text: str) -> tuple[list[Segment], int]:
    """Parse WebVTT text.  Returns (segments, skipped_lines)."""
    # Drop the WEBVTT header line and any NOTE/STYLE/REGION blocks, but
    # keep blank lines — they separate the cues.
    lines = text.splitlines()
    kept_lines: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if in_block:
            if not stripped:
                in_block = False
            continue
        if stripped == "WEBVTT" or stripped.startswith(("Kind:", "Language:")):
            continue
        if stripped.startswith(("NOTE", "STYLE", "REGION")):
            in_block = True
            continue
        kept_lines.append(line)
    # VTT cues look like SRT cues but the timestamp line may carry settings
    # after the end time ("00:01:23.456 --> 00:01:25.000 align:start").
    segments: list[Segment] = []
    skipped = 0
    for block in re.split(r"\r?\n\r?\n", "\n".join(kept_lines).strip()):
        cue_lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not cue_lines:
            continue
        timing_idx = next((i for i, line in enumerate(cue_lines) if "-->" in line), None)
        if timing_idx is None:
            skipped += 1
            continue
        timing = cue_lines[timing_idx].split("-->")
        start_m = _TS_RE.search(timing[0])
        end_m = _TS_RE.search(timing[1]) if len(timing) > 1 else None
        if start_m is None or end_m is None:
            skipped += 1
            continue
        body = _clean(" ".join(cue_lines[timing_idx + 1:]))
        if not body:
            skipped += 1
            continue
        segments.append(
            Segment(
                start=_to_seconds(*start_m.groups()),
                end=_to_seconds(*end_m.groups()),
                text=body,
            )
        )
    segments.sort(key=lambda seg: seg.start)
    return segments, skipped


def parse_paste(text: str) -> tuple[list[Segment], int]:
    """Parse a pasted YouTube transcript (``1:23 some words`` per line).

    A cue ends when the next timestamped line starts.  Lines without a
    timestamp are glued onto the previous cue — auto-caption pastes often
    wrap mid-sentence.
    """
    segments: list[Segment] = []
    skipped = 0
    current: Segment | None = None

    def flush(seg: Segment | None) -> None:
        if seg is not None and seg.text:
            segments.append(seg)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _PASTE_TS_RE.match(line)
        if match is None:
            if current is not None:
                current = Segment(current.start, current.end, current.text + " " + _clean(line))
            else:
                skipped += 1
            continue
        flush(current)
        if match.group("c") is not None:
            # 1:23:45 — hours:minutes:seconds.
            start = _to_seconds(match.group("a"), match.group("b"), match.group("c"))
        else:
            # 1:23 — minutes:seconds.
            start = _to_seconds("0", match.group("a"), match.group("b"))
        current = Segment(start, start, _clean(match.group("text")))
    flush(current)
    # End times: each cue runs until the next one starts (or +10s for the last).
    fixed: list[Segment] = []
    for i, seg in enumerate(segments):
        end = segments[i + 1].start if i + 1 < len(segments) else seg.start + 10
        fixed.append(Segment(seg.start, max(end, seg.start + 1), seg.text))
    return fixed, skipped


def parse_transcript(text: str, filename: str = "") -> tuple[list[Segment], int]:
    """Auto-detect the format and parse.  Raises ParseError on empty input."""
    if not text.strip():
        raise ParseError("transcript is empty")
    lowered = filename.lower()
    if lowered.endswith(".vtt") or text.lstrip().startswith("WEBVTT"):
        segments, skipped = parse_vtt(text)
    elif lowered.endswith(".srt") or "-->" in text:
        segments, skipped = parse_srt(text)
    else:
        segments, skipped = parse_paste(text)
    if not segments:
        raise ParseError(
            "no usable cues found — expected .srt, .vtt, or lines like '1:23 some words'"
        )
    return segments, skipped
