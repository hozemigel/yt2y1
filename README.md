# yt2y1

Download music from YouTube and get it onto an [Innioasis Y1](https://www.innioasis.com/) player, correctly tagged.

Two small tools, each doing one job:

- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3.
- **[y1sync](y1sync/)** — identify, tag, and sync a music library to the Y1 by audio fingerprint rather than filename, so a mislabeled download doesn't end up mislabeled on the device.

`y1sync` can also drive `yt2mp3` for you from its own menu, so in practice
you usually only ever run `y1sync`. Both still work perfectly well on
their own.

## What you need before you start

| Requirement | What it's for | Get it |
|---|---|---|
| **Python 3.10+** | both tools are Python packages | [python.org/downloads](https://www.python.org/downloads/) — on Windows, tick "Add python.exe to PATH" during install |
| **git** | to download this repo | [git-scm.com](https://git-scm.com/downloads) |
| **ffmpeg** | converts downloaded audio to MP3, and is used when decoding audio for tagging | see below |
| **chromaprint** (`fpcalc`) | computes the audio fingerprint y1sync uses to identify tracks accurately | see below |
| **A free AcoustID application key** | looks up what a fingerprint matches | [acoustid.org/new-application](https://acoustid.org/new-application) — see [y1sync's README](y1sync/README.md#setting-up-fingerprinting), it's a two-minute form |
| **The Y1 itself, over USB** | only needed for the last step, sending files to the device | — |

y1sync still works without chromaprint or an AcoustID key — it just falls
back to guessing tags from filenames and asks you to confirm every one,
which is roughly as much effort as tagging by hand. The five minutes of
setup is worth it.

### Installing ffmpeg and chromaprint

```bash
# macOS
brew install ffmpeg chromaprint

# Debian, Ubuntu
sudo apt install ffmpeg libchromaprint-tools

# Windows
# ffmpeg:      https://ffmpeg.org/download.html
# chromaprint: https://acoustid.org/chromaprint (grab the fpcalc build)
# Extract both and add their folders to your PATH (System Properties ->
# Environment Variables -> Path), then open a new terminal so it picks
# up the change.
```

This project has only actually been run on Linux so far — the code
itself isn't tied to it (see [y1sync's Status section](y1sync/README.md#status)
for specifics), but if you're trying it on Windows or macOS for the
first time, budget a little extra patience for this step in particular,
and consider it a genuine bug report if something here doesn't work as
described.

## Install

```bash
git clone https://github.com/hozemigel/yt2y1
cd yt2y1
pip install ./yt2mp3
pip install ./y1sync
```

## First run

```bash
y1sync
```

The first time, it asks where your music folder is and offers to find
one for you — no path-typing required. After that, you get a menu:

```
1. Download from YouTube  (then tag and send to player)
2. Update player  (find new tracks, then send them over)
3. Change music folder
4. Check setup
5. Quit
```

Option **4** ("Check setup") is worth running first — it confirms ffmpeg,
chromaprint and the AcoustID key are all found, and whether the Y1 is
currently detected.

Then option **1** covers the whole flow: paste a YouTube link, pick a
bitrate (or just press Enter for 320kbps), and it downloads, tags, and
sends the track to the Y1 automatically.

See each tool's own README for everything else — [yt2mp3](yt2mp3/README.md)
and [y1sync](y1sync/README.md) — including how y1sync decides which
release to tag a track with, and why it refuses to guess.
