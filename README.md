# yt2y1

Download music from YouTube and get it onto an [Innioasis Y1](https://www.innioasis.com/) player, correctly tagged.

Two small tools, each doing one job:

- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3.
- **[y1sync](y1sync/)** — identify, tag, and sync a music library to the Y1 by audio fingerprint rather than filename, so a mislabeled download doesn't end up mislabeled on the device.

`y1sync` can also drive `yt2mp3` for you from its own menu, so in practice
you usually only ever run `y1sync`. Both still work perfectly well on
their own.

## Windows: one-line install

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-windows.ps1 | iex
```

This installs Python, Git, ffmpeg and chromaprint if any are missing,
downloads yt2y1, installs both tools, pauses partway through to walk you
through the free [AcoustID key](#whats-an-acoustid-key), and finishes by
running `y1sync doctor` so you can see everything is actually ready. It's
safe to run again if anything gets interrupted — already-done steps are
skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-windows.ps1](install-windows.ps1).

## Linux: one-line install

*(Debian/Ubuntu-based systems -- anything with `apt`.)*

Open a terminal and paste:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-linux.sh)"
```

This installs Python, git, ffmpeg and chromaprint via `apt` if any are
missing, downloads yt2y1, installs both tools into one virtual environment
shared between them, adds them to your PATH, pauses partway through to
walk you through the free [AcoustID key](#whats-an-acoustid-key), and
finishes by running `y1sync doctor` so you can see everything is actually
ready. It's safe to run again if anything gets interrupted — already-done
steps are skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-linux.sh](install-linux.sh).

On a non-`apt` distro, the manual steps below work anywhere Python does.

## macOS: one-line install

Open Terminal and paste:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-macos.sh)"
```

This installs Homebrew itself if it's missing, then Python, git, ffmpeg
and chromaprint via Homebrew if any of those are missing, downloads
yt2y1, installs both tools into one virtual environment shared between
them, adds them to your PATH, pauses partway through to walk you through
the free [AcoustID key](#whats-an-acoustid-key), and finishes by running
`y1sync doctor` so you can see everything is actually ready. It's safe to
run again if anything gets interrupted — already-done steps are skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-macos.sh](install-macos.sh).

## What's an AcoustID key?

[AcoustID](https://acoustid.org/) is a free, open audio-fingerprinting
lookup — the same idea as Shazam. It's what lets `y1sync` identify each
track from its actual audio instead of guessing from a messy YouTube
filename, which is the whole reason this tool exists instead of just
renaming files by hand.

Getting a key is free and takes about two minutes. The one-line
installers above open [acoustid.org/new-application](https://acoustid.org/new-application)
in your browser partway through and then pause at a terminal prompt for
you to paste the key back in — that's the only part of installing that
needs you at the keyboard. AcoustID issues two different kinds of key
and it's easy to grab the wrong one; the installers link straight to the
right page, so just following the link they open is enough. Setting it
up by hand instead? See [y1sync's README](y1sync/README.md#setting-up-fingerprinting)
for the two-key mixup to avoid and where the key is stored.

## What you need before you start

*(Any other Linux or package manager, or if you want to install by hand
instead.)*

| Requirement | What it's for | Get it |
|---|---|---|
| **Python 3.10+** | both tools are Python packages | [python.org/downloads](https://www.python.org/downloads/) — on Windows, tick "Add python.exe to PATH" during install |
| **git** | to download this repo | [git-scm.com](https://git-scm.com/downloads) |
| **ffmpeg** | converts downloaded audio to MP3, and is used when decoding audio for tagging | see below |
| **chromaprint** (`fpcalc`) | computes the audio fingerprint y1sync uses to identify tracks accurately | see below |
| **A free AcoustID application key** | identifies tracks by their actual audio, not by filename — see [above](#whats-an-acoustid-key) | [acoustid.org/new-application](https://acoustid.org/new-application), a two-minute form |
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

Both tools have been run end-to-end on Windows and on Linux; macOS hasn't
been tried yet but the code isn't tied to either platform (see
[y1sync's Status section](y1sync/README.md#status) for specifics). The
Windows install script above automates the steps that were manually
verified working, but the automation itself is newer than those steps
individually — if it trips on something, that's a genuine bug report,
and the manual table above is the fallback in the meantime.

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
