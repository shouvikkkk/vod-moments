"""Command line interface for vod-moments.

Usage (the whole tool is one command):

    python -m vodmoments find stream.srt
    python -m vodmoments find stream.srt --audio stream.mp4 --top 15
    python -m vodmoments find --audio stream.mp4 --cut
    python -m vodmoments find stream.vtt --format json --out moments.json

No captions?  ``find --audio stream.mp4`` works on sound alone — the
transcript is optional whenever ``--audio`` is given.  Add ``--cut`` to
actually cut the clips out of the video instead of just listing them.

Exit codes: 0 = moments found, 1 = no moments found (the stream was
quiet), 2 = bad usage or unreadable transcript, 3 = audio problem
(ffmpeg missing or the media file unreadable).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys

from . import __version__
from .audio import AudioError, find_audio_moments
from .cut import CutError, cut_clips
from .merge import merge_moments
from .parse import ParseError, parse_transcript
from .score import Moment, find_transcript_moments


def _fmt_time(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _ffmpeg_cut(moment: Moment, media: str | None) -> str:
    if not media:
        return ""
    return (
        f"ffmpeg -ss {_fmt_time(moment.start)} -to {_fmt_time(moment.end)} "
        f"-i {media} -c copy clip-{_fmt_time(moment.start).replace(':', '')}.mp4"
    )


def render_text(moments: list[Moment], source: str, media: str | None) -> str:
    lines = [f"Top moments in {source} ({len(moments)} found)", ""]
    for i, moment in enumerate(moments, 1):
        lines.append(
            f"{i}. {_fmt_time(moment.start)} – {_fmt_time(moment.end)}"
            f"  score {moment.score}  [{'; '.join(moment.reasons)}]"
        )
        if moment.quote:
            lines.append(f'   "{moment.quote}"')
        if moment.clip:
            lines.append(f"   → {moment.clip}")
        else:
            cut = _ffmpeg_cut(moment, media)
            if cut:
                lines.append(f"   {cut}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(moments: list[Moment], source: str) -> str:
    payload = {
        "source": source,
        "moments": [
            {
                "start": round(m.start, 1),
                "end": round(m.end, 1),
                "start_hms": _fmt_time(m.start),
                "end_hms": _fmt_time(m.end),
                "score": m.score,
                "reasons": m.reasons,
                "quote": m.quote,
                "spoiler_hint": m.spoiler_hint,
                "signal": m.source,
                "clip": m.clip or None,
            }
            for m in moments
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_csv(moments: list[Moment]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["start", "end", "score", "reasons", "quote", "spoiler_hint", "signal", "clip"])
    for m in moments:
        writer.writerow([
            _fmt_time(m.start),
            _fmt_time(m.end),
            m.score,
            "; ".join(m.reasons),
            m.quote,
            "yes" if m.spoiler_hint else "no",
            m.source,
            m.clip,
        ])
    return buffer.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vod-moments",
        description=(
            "Find the funny moments in a long stream without rewatching it. "
            "Give it the stream's captions (.srt, .vtt, or a pasted transcript) "
            "and, optionally, the video or audio file itself.  No captions? "
            "Pass --audio alone and it works from sound."
        ),
    )
    parser.add_argument("--version", action="version", version=f"vod-moments {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("find", help="rank the best moments in a stream")
    find.add_argument("transcript", nargs="?", default=None,
                      help="captions file: .srt, .vtt, or pasted transcript text "
                           "(optional when --audio is given)")
    find.add_argument("--audio", metavar="MEDIA", default=None,
                      help="video/audio file to scan for loud spikes too (needs ffmpeg)")
    find.add_argument("--cut", metavar="DIR", nargs="?", const="clips", default=None,
                      help="actually cut each moment into a clip file in DIR "
                           "(default: clips; needs --audio)")
    find.add_argument("--top", type=int, default=10,
                      help="how many moments to list (default 10)")
    find.add_argument("--min-gap", type=float, default=60.0,
                      help="minimum seconds between two moments (default 60)")
    find.add_argument("--format", choices=["text", "json", "csv"], default="text",
                      help="output format (default text)")
    find.add_argument("--out", metavar="FILE", default=None,
                      help="write the list to a file instead of printing it")
    find.add_argument("--hide-spoilers", action="store_true",
                      help="leave out moments flagged as possible story moments")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "find":
        parser.print_help()
        return 2
    if args.top < 1:
        print("error: --top must be at least 1", file=sys.stderr)
        return 2
    if args.min_gap < 0:
        print("error: --min-gap cannot be negative", file=sys.stderr)
        return 2
    if args.transcript is None and args.audio is None:
        print("error: give it a transcript file, or --audio with a video/audio "
              "file (or both)", file=sys.stderr)
        return 2
    if args.cut is not None and args.audio is None:
        print("error: --cut needs --audio — the video or audio file to cut "
              "the clips from", file=sys.stderr)
        return 2

    segments: list = []
    skipped = 0
    if args.transcript is not None:
        try:
            with open(args.transcript, encoding="utf-8", errors="replace") as handle:
                raw = handle.read()
        except OSError as exc:
            print(f"error: cannot read {args.transcript}: {exc.strerror}", file=sys.stderr)
            return 2
        try:
            segments, skipped = parse_transcript(raw, args.transcript)
        except ParseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    moments = find_transcript_moments(
        segments, top=args.top, min_gap=args.min_gap
    )
    if args.audio:
        try:
            audio_moments, audio_duration = find_audio_moments(
                args.audio, top=args.top, min_gap=args.min_gap
            )
        except AudioError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        moments = merge_moments(moments, audio_moments, top=args.top)

    if args.hide_spoilers:
        moments = [m for m in moments if not m.spoiler_hint]

    if skipped:
        print(f"note: skipped {skipped} line(s) I could not read in the transcript",
              file=sys.stderr)
    if not moments:
        print("No moments found — this stretch of the stream was quiet. "
              "Try a longer transcript, or a lower --top.", file=sys.stderr)
        return 1

    source = args.transcript or args.audio
    if args.cut is not None:
        try:
            results = cut_clips(moments, args.audio, args.cut)
        except CutError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        made = [r for r in results if r.ok]
        for result in results:
            if not result.ok:
                print(f"warning: could not cut {result.path}: {result.error}",
                      file=sys.stderr)
        # stderr, not stdout: stdout is the machine-readable list when
        # --format json/csv is used, and must stay clean.
        print(f"Cut {len(made)} clip(s) into {args.cut}/", file=sys.stderr)
        if not made:
            print("warning: no clips were cut — the list below is timestamps only",
                  file=sys.stderr)

    if args.format == "json":
        output = render_json(moments, source)
    elif args.format == "csv":
        output = render_csv(moments)
    else:
        output = render_text(moments, source, args.audio)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(output)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc.strerror}", file=sys.stderr)
            return 2
        print(f"Wrote {len(moments)} moment(s) to {args.out}")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
