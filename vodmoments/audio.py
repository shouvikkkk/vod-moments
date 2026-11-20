"""Find loud moments in a stream's audio — the crashes, screams and
celebrations that happen while nobody is talking.

Transcript-only clippers miss exactly these moments: a crash, a chase, a
streamer screaming at a silent screen.  Sound finds them.  The method is
deliberate signal processing, not a model:

* ffmpeg turns the media into 16 kHz mono WAV (ffmpeg is the only external
  tool; it is already on most clippers' machines).
* We read the WAV in small chunks and measure the RMS loudness of each
  half-second.
* A chunk is a *spike* when it is much louder than the stream's own recent
  baseline **and** it rises fast **and** it is spiky (high crest factor),
  not merely loud.  Licensed in-game radio is loud and sustained — low
  crest, slow rise — so it is rejected.  A crash is loud, sudden and
  spiky, so it is kept.
* The file is processed streaming, chunk by chunk, so a 12-hour VOD never
  sits in memory whole.

Honest limit, stated in the README too: a spike is a *candidate* moment,
not a guaranteed banger.  The human still picks.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass

from .score import Moment

SAMPLE_RATE = 16000
CHUNK_SECONDS = 0.5
FRAMES_PER_CHUNK = int(SAMPLE_RATE * CHUNK_SECONDS)

# A chunk counts as a spike when it clears all three of these.
SPIKE_RATIO = 3.0  # RMS vs the stream's own recent baseline
MIN_RISE = 2.0  # RMS vs the previous 5 seconds
MIN_CREST = 2.5  # peak / RMS inside the chunk (spiky, not sustained)
ABSOLUTE_FLOOR = 0.02  # ignore near-silence entirely (16-bit scale 0..1)
SETUP_SECONDS = 15.0  # keep the setup before the spike
PAYOFF_SECONDS = 15.0  # keep the payoff after it
MERGE_SECONDS = 20.0  # spikes this close together are one moment
BASELINE_SECONDS = 600.0  # baseline window: 10 minutes either side


class AudioError(RuntimeError):
    """Raised when audio cannot be read (ffmpeg missing, bad file)."""


@dataclass
class _Chunk:
    time: float
    rms: float
    crest: float


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_wav(media_path: str) -> str:
    """Use ffmpeg to decode ``media_path`` to a temp 16 kHz mono WAV.

    Returns the temp path (caller deletes it).  Raises AudioError with a
    plain-language message when ffmpeg is missing or the file is unreadable.
    """
    if not _ffmpeg_available():
        raise AudioError(
            "ffmpeg was not found — install it to use --audio "
            "(https://ffmpeg.org/download.html), or run without --audio "
            "to find moments from the transcript alone"
        )
    if not os.path.isfile(media_path):
        raise AudioError(f"no such media file: {media_path}")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", media_path,
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", tmp.name,
        ],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if proc.returncode != 0 or not os.path.getsize(tmp.name):
        os.unlink(tmp.name)
        detail = (proc.stderr or "").strip().splitlines()
        raise AudioError(
            "ffmpeg could not read "
            f"{media_path}: {detail[-1] if detail else 'unknown error'}"
        )
    return tmp.name


def read_chunks(wav_path: str) -> tuple[list[_Chunk], float]:
    """Stream a WAV file into half-second (time, rms, crest) chunks."""
    chunks: list[_Chunk] = []
    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        if width != 2:
            raise AudioError(f"unsupported sample width {width} (expected 16-bit)")
        frames_per_chunk = int(rate * CHUNK_SECONDS)
        index = 0
        while True:
            raw = wav.readframes(frames_per_chunk)
            if not raw:
                break
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)
            if channels > 1:
                samples = samples[::channels]
            if not samples:
                break
            peak = max(abs(s) for s in samples) / 32768.0
            mean_sq = sum((s / 32768.0) ** 2 for s in samples) / len(samples)
            rms = math.sqrt(mean_sq)
            crest = (peak / rms) if rms > 1e-6 else 0.0
            chunks.append(_Chunk(time=index * CHUNK_SECONDS, rms=rms, crest=crest))
            index += 1
    duration = len(chunks) * CHUNK_SECONDS
    return chunks, duration


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def find_audio_moments(
    media_path: str,
    top: int = 10,
    min_gap: float = 60.0,
) -> tuple[list[Moment], float]:
    """Rank loud-spike moments in a media file.  Returns (moments, duration)."""
    wav_path = extract_wav(media_path)
    try:
        chunks, duration = read_chunks(wav_path)
    finally:
        os.unlink(wav_path)
    if not chunks:
        return [], duration

    baseline_span = int(BASELINE_SECONDS / CHUNK_SECONDS)
    events: list[tuple[float, float, float]] = []  # (start, end, score)
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        # Baseline: the median loudness of the surrounding 10 minutes,
        # excluding this chunk itself — the stream sets its own bar.
        lo = max(0, i - baseline_span)
        hi = min(len(chunks), i + baseline_span)
        neighbours = [c.rms for j, c in enumerate(chunks[lo:hi], start=lo) if j != i]
        baseline = _median(neighbours) if neighbours else 0.0
        # Recent level: the last 5 seconds, for the rise check.
        recent = [c.rms for c in chunks[max(0, i - 10):i]]
        recent_level = _median(recent) if recent else baseline
        # A near-silent baseline is not "no spike possible" — it is the
        # quiet-driving case, where any loud chunk is a spike by definition.
        # Floor both denominators at the audibility floor so silence never
        # divides the signal away.
        ratio = chunk.rms / max(baseline, ABSOLUTE_FLOOR)
        rise = chunk.rms / max(recent_level, ABSOLUTE_FLOOR)
        if (
            chunk.rms >= ABSOLUTE_FLOOR
            and ratio >= SPIKE_RATIO
            and rise >= MIN_RISE
            and chunk.crest >= MIN_CREST
        ):
            # Log scale, capped: a spike in a silent file is strong, but
            # 100 is reserved for a moment both signals agree on (see merge).
            strength = min(
                95,
                int(
                    25
                    + 12 * math.log2(min(ratio, 32.0))
                    + 6 * math.log2(min(rise, 16.0))
                ),
            )
            events.append((chunk.time, chunk.time + CHUNK_SECONDS, float(strength)))
        i += 1

    # Merge spikes close together into one moment.
    merged: list[list[float]] = []
    for start, end, strength in events:
        if merged and start - merged[-1][1] <= MERGE_SECONDS:
            merged[-1][1] = end
            merged[-1][2] = max(merged[-1][2], strength)
        else:
            merged.append([start, end, strength])

    moments: list[Moment] = []
    for start, end, strength in merged:
        moments.append(
            Moment(
                start=max(0.0, start - SETUP_SECONDS),
                end=min(duration, end + PAYOFF_SECONDS),
                score=int(min(100, strength)),
                reasons=["sudden loud spike in the audio"],
                quote="",
                spoiler_hint=False,
                source="audio",
            )
        )
    moments.sort(key=lambda m: (-m.score, m.start))
    kept: list[Moment] = []
    for cand in moments:
        if all(abs(cand.start - other.start) >= min_gap for other in kept):
            kept.append(cand)
        if len(kept) >= top:
            break
    kept.sort(key=lambda m: m.start)
    return kept, duration
