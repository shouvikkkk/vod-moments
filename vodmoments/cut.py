"""Actually cut the ranked moments out of the media file.

v0.1 only printed an ffmpeg command for each moment — a to-do list, not
clips.  With ``--cut`` the tool runs that command itself, once per moment,
and hands back real clip files.

The cut is a stream copy (``-c copy``): fast, no re-encode, no quality
loss.  Two honest consequences of that choice, stated in the README too:

* A video cut lands on the nearest keyframe at or before the moment's
  start, so a clip can begin a fraction of a second early.  Audio cuts
  are sample-accurate.  Either way the clipper trims in their editor.
* The output keeps the input's container (``.mp4`` in → ``.mp4`` out,
  ``.wav`` in → ``.wav`` out), because a copied stream cannot change
  containers.

A failed cut never aborts the run: the failure is recorded on the result
and reported as a warning, and the other clips still get made.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from .score import Moment


class CutError(RuntimeError):
    """Raised when clips cannot be made at all (no media, bad folder)."""


@dataclass
class CutResult:
    """One attempted cut: the moment, the file, and what happened."""

    moment: Moment
    path: str  # where the clip was meant to go
    ok: bool
    error: str = ""  # plain-language reason when ok is False


def _clip_name(moment: Moment, ext: str, taken: set[str]) -> str:
    """``clip-000315.mp4`` — the moment's start as HHMMSS, made unique."""
    total = int(moment.start)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    base = f"clip-{hours:02d}{minutes:02d}{secs:02d}"
    name = base + ext
    suffix = 2
    while name in taken:
        name = f"{base}-{suffix}{ext}"
        suffix += 1
    taken.add(name)
    return name


def cut_clips(
    moments: list[Moment],
    media: str,
    out_dir: str,
) -> list[CutResult]:
    """Cut each moment out of ``media`` into ``out_dir``.  Returns one
    CutResult per moment, in the same order.  Sets ``moment.clip`` to the
    file path on success (empty string otherwise)."""
    if not moments:
        return []
    if not os.path.isfile(media):
        raise CutError(f"no such media file: {media}")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        raise CutError(f"cannot create clips folder {out_dir}: {exc.strerror}")
    _, ext = os.path.splitext(media)
    ext = ext.lower() or ".mp4"
    taken: set[str] = set()
    results: list[CutResult] = []
    for moment in moments:
        name = _clip_name(moment, ext, taken)
        path = os.path.join(out_dir, name)
        duration = moment.end - moment.start
        if duration <= 0:
            results.append(CutResult(moment, path, False, "moment has no length"))
            continue
        proc = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-y",
                "-ss", f"{moment.start:.1f}",
                "-i", media,
                "-t", f"{duration:.1f}",
                "-c", "copy", path,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0 or not os.path.isfile(path):
            detail = (proc.stderr or "").strip().splitlines()
            results.append(CutResult(
                moment, path, False,
                detail[-1] if detail else "ffmpeg failed for an unknown reason",
            ))
            continue
        moment.clip = path
        results.append(CutResult(moment, path, True))
    return results
