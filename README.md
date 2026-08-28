# yt2y1

Download music from YouTube and get it onto an [Innioasis Y1](https://www.innioasis.com/) player, correctly tagged.

Two small tools, each doing one job:

- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3,
  and drop a small `.yt2mp3.json` sidecar of what YouTube said the track
  was next to each file.
- **[y1sync](y1sync/)** — identify, tag, and sync a music library to the Y1 by audio fingerprint rather than filename, so a mislabeled download doesn't end up mislabeled on the device.

`y1sync` can also drive `yt2mp3` for you from its own menu, so in practice
you usually only ever run `y1sync`. Both still work perfectly well on
their own.

## Windows: one-line install

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-windows.ps1 | iex
```

This installs Python, Git, ffmpeg, chromaprint and deno (a JS runtime
yt-dlp uses for reliable YouTube downloads) if any are missing, downloads
yt2y1, installs both tools, and finishes by running `y1sync
doctor` so you can see everything is actually ready. There's nothing to
type partway through — audio fingerprinting works out of the box (see
[below](#how-does-it-identify-tracks)). It's safe to run again if
anything gets interrupted — already-done steps are skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-windows.ps1](install-windows.ps1).

## Linux: one-line install

*(Debian/Ubuntu-based systems -- anything with `apt`.)*

Open a terminal and paste:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-linux.sh)"
```

This installs Python, git, ffmpeg and chromaprint via `apt`, plus deno (a
JS runtime yt-dlp uses for reliable YouTube downloads) via its own
installer, if any are missing, downloads yt2y1, installs both tools into
one virtual environment
shared between them, adds them to your PATH, and finishes by running
`y1sync doctor` so you can see everything is actually ready. There's
nothing to type partway through — audio fingerprinting works out of the
box (see [below](#how-does-it-identify-tracks)). It's safe to run again if
anything gets interrupted — already-done steps are skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-linux.sh](install-linux.sh).

On a non-`apt` distro, the manual steps below work anywhere Python does.

## macOS: one-line install

Open Terminal and paste:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hozemigel/yt2y1/main/install-macos.sh)"
```

This installs Homebrew itself if it's missing, then Python, git, ffmpeg,
chromaprint and deno (a JS runtime yt-dlp uses for reliable YouTube
downloads) via Homebrew if any of those are missing, downloads
yt2y1, installs both tools into one virtual environment shared between
them, adds them to your PATH, and finishes by running `y1sync doctor` so
you can see everything is actually ready. There's nothing to type partway
through — audio fingerprinting works out of the box (see
[below](#how-does-it-identify-tracks)). It's safe to run again if
anything gets interrupted — already-done steps are skipped.

If you'd rather see what it does before running it, the script itself is
right here: [install-macos.sh](install-macos.sh).

## How does it identify tracks?

By audio fingerprint, through [AcoustID](https://acoustid.org/) — a free,
open lookup, the same idea as Shazam. That's what lets `y1sync` identify
each track from its actual audio instead of guessing from a messy YouTube
filename, which is the whole reason this tool exists instead of just
renaming files by hand.

There's nothing to sign up for. AcoustID's lookup is keyed to the
application, not to you, so `y1sync` ships with its own key and
fingerprinting just works. If that key is ever rate-limited you can drop
your own into `~/.config/y1sync/config.toml` — see
[y1sync's README](y1sync/README.md#setting-up-fingerprinting) — but you
will almost certainly never need to.

## What you need before you start

*(Any other Linux or package manager, or if you want to install by hand
instead.)*

| Requirement | What it's for | Get it |
|---|---|---|
| **Python 3.10+** | both tools are Python packages | [python.org/downloads](https://www.python.org/downloads/) — on Windows, tick "Add python.exe to PATH" during install |
| **git** | to download this repo | [git-scm.com](https://git-scm.com/downloads) |
| **ffmpeg** | converts downloaded audio to MP3, and is used when decoding audio for tagging | see below |
| **chromaprint** (`fpcalc`) | computes the audio fingerprint y1sync uses to identify tracks accurately | see below |
| **deno** (or another JS runtime) | yt-dlp uses it to extract YouTube reliably; without one, downloads still work but time out and fail more often | see below |
| **The Y1 itself, over USB** | only needed for the last step, sending files to the device | — |

The AcoustID lookup y1sync uses to identify tracks needs no account — a
key is built in (see [above](#how-does-it-identify-tracks)). y1sync still
works without chromaprint too; it just falls back to guessing tags from
filenames and asks you to confirm every one, which is roughly as much
effort as tagging by hand. Installing it is worth it. deno is the same
kind of thing: not a hard requirement, but skipping it makes YouTube
downloads slower and more prone to failing partway through.

### Installing ffmpeg, chromaprint and deno

```bash
# macOS
brew install ffmpeg chromaprint deno

# Debian, Ubuntu
sudo apt install ffmpeg libchromaprint-tools
curl -fsSL https://deno.land/install.sh | sh   # deno isn't packaged in apt

# Windows
# ffmpeg:      https://ffmpeg.org/download.html
# chromaprint: https://acoustid.org/chromaprint (grab the fpcalc build)
# deno:        winget install DenoLand.Deno
# Extract ffmpeg and chromaprint and add their folders to your PATH
# (System Properties -> Environment Variables -> Path), then open a new
# terminal so it picks up the change.
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
5. Check for updates
6. Quit
```

Option **4** ("Check setup") is worth running first — it confirms ffmpeg
and chromaprint are found, and whether the Y1 is currently detected.

Then option **1** covers the whole flow: paste a YouTube link, pick a
bitrate (or just press Enter for 320kbps), and it downloads, tags, and
sends the track to the Y1 automatically.

See each tool's own README for everything else — [yt2mp3](yt2mp3/README.md)
and [y1sync](y1sync/README.md) — including how y1sync decides which
release to tag a track with, and why it refuses to guess.
