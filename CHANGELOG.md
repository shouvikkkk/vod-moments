# Changelog

## 0.2.0 — 2026-11-22

- **Audio-only mode.** The transcript is now optional: `find --audio stream.mp4`
  works from sound alone. Before this, the README promised a stream with no
  captions "needs the --audio mode" while the tool refused to run without a
  transcript file — that contradiction is fixed.
- **`--cut` actually cuts the clips.** `find --audio stream.mp4 --cut` writes
  real clip files (`clips/clip-000315.mp4`, …) instead of printing ffmpeg
  commands to paste by hand. `--cut my-clips` picks another folder. Cuts are
  stream copies (`-c copy`, no re-encode); video cuts land on the nearest
  keyframe at or before the moment's start, audio cuts are exact. A failed
  cut is reported as a warning and never aborts the other clips.
- The moment list now shows the clip file (`→ clips/clip-000315.mp4`) when one
  was cut, and JSON/CSV output gains a `clip` field (null/empty when no cut
  was made). The "Cut N clip(s)" summary goes to stderr so `--format json`
  output stays clean.

## 0.1.0 — 2026-11-20

- First release: transcript scoring (English + Hinglish), audio spike
  detection, merge with agreement boost, text/JSON/CSV output.
