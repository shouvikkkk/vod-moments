# vod-moments

**Find the funny moments in a long GTA 6 stream without rewatching the whole thing.**

You watched — or missed — a 4-hour stream. Somewhere in it there are four or five moments worth clipping: a crash, a chase, the streamer losing it laughing. Finding them by scrubbing takes longer than the stream itself, so most moments never get posted. This tool reads the stream's captions (or listens to its sound) and hands you a ranked list of timestamps, with a reason for each one. Free, offline, no account, no upload.

## The problem

> "Scrubbing a four-hour VOD for highlights can take longer than the stream itself, so most moments never get posted." — [aiclipmaker](https://aiclipmaker.app/gta-6-highlights)

Every tool that does this today charges for it: aiclipmaker is about 1 cent per minute of video plus credits per clip, OpusClip and Eklipse are monthly subscriptions, and StoryCut's free tier refuses videos with almost no speech — which is exactly what a GTA 6 crash looks like: two seconds of silence, then everyone screaming. This tool is the free, offline version, and it is built for that silent-gameplay case on purpose.

## How to use it

You need Python 3.10 or newer. Nothing else to install for the basic version.

**1. Get the stream's captions.** On YouTube, open the video, click the three dots under it → **Show transcript** → copy the text into a file, or download the captions as `.srt` / `.vtt`. (YouTube gives these away free — no key, no account needed beyond watching the video.) Twitch and Kick VODs work the same way if you have their caption file.

**2. Run one command:**

```bash
python -m vodmoments find stream.srt
```

**3. You get a ranked shot list:**

```
Top moments in stream.srt (3 found)

1. 00:00:55 – 00:01:35  score 66  [lots of laughing; shocked reaction; Hinglish reaction]
   "wait wait wait did you see that guy"

2. 00:03:15 – 00:03:55  score 60  [laughing; shocked reaction; chase / crash / cops; shouting (ALL CAPS)]
   "WASTED no no no what just happened"

3. 00:05:25 – 00:06:05  score 54  [laughing; shocked reaction; shouting (ALL CAPS)]
   "OH MY GOD HE FLEW OFF THE BRIDGE HAHAHA"
```

Each moment starts a few seconds before the funny bit (the setup) and ends a few seconds after it (the payoff). Take the timestamps straight into your editor.

**No captions? Use sound alone.** Twitch and Kick VODs often have no caption file at all — that used to stop the tool cold. Now the transcript is optional: give it just the video and it works from sound.

```bash
python -m vodmoments find --audio stream.mp4
```

**Get the clips, not just the timestamps.** Add `--cut` and the tool cuts each moment out of the video for you, into a `clips/` folder — real files you can post, not commands to paste:

```bash
python -m vodmoments find --audio stream.mp4 --cut
# Cut 3 clip(s) into clips/
# clips/clip-000315.mp4  clips/clip-000555.mp4  clips/clip-000835.mp4
```

`--cut my-clips` picks a different folder. The clips keep the video's own format (`.mp4` in → `.mp4` out), and the cut is a fast stream copy — no re-encode, no quality loss.

## Find moments from sound too

The captions catch jokes and shouted lines. They miss the moments where nobody is talking — a crash, a chase, a scream. If you have the video or audio file, add `--audio` and the tool listens as well:

```bash
python -m vodmoments find stream.srt --audio stream.mp4 --top 15
```

This needs [ffmpeg](https://ffmpeg.org/download.html) installed (one download; most clippers already have it). It measures loudness half-second by half-second and flags sudden spikes — a crash, not the in-game radio, which is loud but steady. When the words and the sound agree on the same moment, it scores higher. With `--audio`, every moment also prints a ready-to-paste `ffmpeg` cut command:

```
ffmpeg -ss 00:03:15 -to 00:03:55 -i stream.mp4 -c copy clip-000315.mp4
```

## Options

| Option | What it does |
|---|---|
| `--top 15` | List 15 moments instead of 10 |
| `--min-gap 30` | Allow moments 30 seconds apart instead of 60 |
| `--format json` | Machine-readable output (for scripts) |
| `--format csv` | A spreadsheet of moments |
| `--out moments.txt` | Save the list to a file instead of printing it |
| `--hide-spoilers` | Leave out moments flagged as possible story beats |
| `--audio FILE` | Also scan the video/audio for loud spikes; works alone, with no captions at all |
| `--cut [DIR]` | Actually cut each moment into a clip file in DIR (default `clips/`; needs `--audio`) |

Exit codes: `0` moments found, `1` the stream was quiet (no moments), `2` the transcript could not be read, `3` audio problem (ffmpeg missing or the media file unreadable).

## What the scores mean

A moment scores 0–100 from plain signals a human would use: laughing (`haha`, `lol`, `lmao`), shock (`WASTED`, `oh my god`, `clip it`, `no no no`), game events (cops, chase, crash, wanted level), shouting in ALL CAPS, and Hinglish reactions (`arre`, `bhai`, `pagal`) — Indian creators' streams mix Hindi and English, and the scorer reads both. A window needs a real cluster of signals to count; one stray word never decides it. Audio spikes need three things at once: much louder than the stream's own recent level, a fast rise, and a spiky (not sustained) shape — so the radio doesn't count.

Moments that mention story words (`ending`, `dies`, `betrayal`, `plot twist`) are flagged `possible story moment — check before posting`, so you don't accidentally clip a spoiler in launch week. They are never hidden unless you pass `--hide-spoilers`.

## Honest limitations

- **A spike is a candidate, not a guaranteed banger.** The tool finds where the stream got loud or funny-sounding; you still pick what to post. That is the whole point — it does the scrubbing, you do the taste.
- **It is only as good as the captions.** Auto-captions mis-hear words, especially names and slang. The scorer uses families of words, not exact phrases, so one mis-hearing rarely kills a moment — but a stream with no captions at all runs on sound alone (`--audio` with no transcript).
- **Audio mode needs ffmpeg**, and it reads the whole file once to decode it, so a 12-hour VOD takes a couple of minutes to scan. The transcript mode is instant.
- **A `--cut` video clip starts on the nearest keyframe at or before the moment's start**, so it can begin a fraction of a second early — that is the price of a fast stream copy with no re-encode. Audio cuts are exact. Trim the rough edge in your editor, as you would anyway.
- **It does not download anything.** You bring the captions and the video; the tool never touches the network, your accounts, or any API.

## How it differs from the paid tools

| | vod-moments | aiclipmaker / OpusClip / Eklipse |
|---|---|---|
| Price | Free, forever | Credits or subscription |
| Account / upload | None — runs on your computer | Account + upload your video |
| Silent gameplay (crash, no talking) | Found by the audio spike detector | Transcript-first tools miss or refuse it |
| Hinglish streams | Scored in English + Roman-script Hinglish | Varies |
| Output | Timestamps + reasons + real clip files (`--cut`) | Vertical clips, in their editor |

## For developers

```bash
python -m unittest discover -s tests   # 58 tests, all green
```

- `vodmoments/parse.py` — `.srt`, `.vtt` and pasted-transcript parsers (bad lines skipped, never fatal)
- `vodmoments/score.py` — 30-second sliding-window transcript scorer + non-max suppression
- `vodmoments/audio.py` — ffmpeg → WAV, streaming RMS/crest spike detector
- `vodmoments/merge.py` — boosts moments both signals agree on
- `vodmoments/cut.py` — cuts the ranked moments out of the media file (`-c copy`, no re-encode)
- `vodmoments/cli.py` — `find` command, text/JSON/CSV output, audio-only mode, `--cut`, exit codes

Try it on the included example: `python -m vodmoments find examples/gta6-stream.srt` — a made-up 7-minute GTA 6 stream with three planted moments (a laugh, a WASTED crash, a bridge jump).

## License

MIT — see [LICENSE](LICENSE). Not affiliated with Rockstar Games or Take-Two Interactive.
