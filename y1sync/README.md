# y1sync

Prepare and sync music libraries for the [Innioasis Y1](https://www.innioasis.com/) player.

The Y1 groups its library by ID3 tags and shows embedded cover art. MP3s
ripped from YouTube arrive with no tags at all, so the device shows a flat
list of filenames under "Unknown Artist". y1sync fixes that.

## Why not use beets or Picard?

Both are excellent and both are general-purpose. Neither knows what the Y1
needs: ID3v2.3 rather than v2.4, FAT32-safe filenames, and the device's
folder layout. y1sync does one job for one player.

## What makes it accurate

Tracks are identified by an audio fingerprint, not by their filename.
Filename-based lookup is what makes naive tagging unreliable — in the
15-track library that motivated this tool, it misidentified 4 of them,
including a 2020 re-recording in place of the 2000 original.

When a recording appears on several releases, y1sync ranks the original
album above compilations and remasters, then asks you to confirm. It does
not guess.

## Requirements

- **Python 3.10+**
- **ffmpeg** and **chromaprint** (`fpcalc`) — see [Setting up fingerprinting](#setting-up-fingerprinting) below
- A free **AcoustID application key** — same section
- To actually copy files to the device: the Y1 connected over USB and mounted as a drive (Windows/macOS/Linux all do this automatically)

## Install

Until the first PyPI release, install from source:

```bash
pip install ./y1sync
```

(from the root of this repo — clone it first: `git clone https://github.com/hozemigel/yt2y1 && cd yt2y1`)

To also get the "Download from YouTube" option in the menu, install the
sibling tool too:

```bash
pip install ./yt2mp3
```

y1sync works fine without it — that menu option just explains how to
install yt2mp3 if you pick it before it's there.

### Setting up fingerprinting

Fingerprinting is what makes y1sync accurate, and it needs three things.

**1. ffmpeg**, used to decode audio:

```bash
sudo apt install ffmpeg    # Debian, Ubuntu
brew install ffmpeg        # macOS
```

Windows: download a build from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
and add its `bin` folder to your PATH.

**2. chromaprint**, which computes the fingerprint:

```bash
sudo apt install libchromaprint-tools    # Debian, Ubuntu
brew install chromaprint                 # macOS
```

Windows: grab the `fpcalc` build from [acoustid.org/chromaprint](https://acoustid.org/chromaprint)
and add its folder to your PATH too.

**3. An AcoustID *application* key.**

AcoustID issues two different keys and it is easy to take the wrong one.
The page at `acoustid.org/api-key`, headed *"Your API Key"*, gives a key
for **submitting** fingerprints — it will not work here, and the service
answers `invalid API key`.

The key you need comes from **[acoustid.org/new-application](https://acoustid.org/new-application)**.
That page shows a short form rather than a key: fill in a name and
version, register, and the key then appears under *My Applications*.

```toml
# ~/.config/y1sync/config.toml
acoustid_key = "your-application-key"
```

Run `y1sync doctor` to confirm both are found.

y1sync still works without either. It falls back to guessing from the
filename, and every track then goes through review — which is roughly
what tagging by hand costs, so it is worth the five minutes of setup.

## Use

The easiest way is to just run it with no arguments:

```bash
y1sync
```

The first time, it asks where your music folder is (offering folders it
finds on disk as numbered choices, so you never have to type a path) and
remembers the answer. After that you get a menu:

```
1. Download from YouTube  (then tag and send to player)
2. Update player  (find new tracks, then send them over)
3. Change music folder
4. Check setup
5. Quit
```

Option 1 needs yt2mp3 installed (see [Install](#install)); it asks for a
YouTube URL and a bitrate, downloads, and runs the same tag-and-send flow
as option 2 automatically.

For scripting, or if you'd rather control each step yourself, the
underlying commands still work directly:

```bash
y1sync doctor              # check dependencies and find the device
y1sync scan ~/Music        # identify, tag and rename
y1sync sync ~/Music        # copy to the Y1
```

### How a scan decides

A fingerprint identifies *which recording* a file holds. It cannot say
which release you want it filed under, because one recording appears on
the original album, on compilations, and on remasters. So:

- fingerprint matched, one release → tagged automatically
- fingerprint matched, several releases → you choose, originals listed first
- no fingerprint, only a filename guess → you always choose

`--yes` skips the middle case, taking the top-ranked release. It will
**not** accept a filename guess: nothing has confirmed the file even holds
that track, and accepting one unseen is how a library ends up with the
wrong artist. Those tracks are left untagged and listed at the end.

Add `--dry-run` to `scan` or `sync` to see what would change without
writing anything:

```bash
y1sync scan ~/Music --dry-run
```

The flag belongs to the subcommand, so it goes after it.

## Safety

`sync` is the only command that writes to the device. It refuses to write
unless the target carries the Y1 folder signature and is a FAT32 volume,
backs up before the first change, writes through a temporary file, and
flushes to disk before reporting success.

Backups go to `~/.local/share/y1sync/backups/`, never to the device.

## Status

Tested end to end against the real AcoustID and MusicBrainz services and
against an Innioasis Y1: `doctor` finds the device, `scan` tags and
renames with cover art, `sync` backs up before writing and leaves no
partial files behind.

The device's own library screen was checked too: synced tracks appear
under the right artist with their cover art showing.

Only one Y1 and one firmware version have been tested. If yours renders
something unexpected after a sync, that is worth an issue — include the
firmware version.

Run end-to-end on Windows as well as Linux, including a real sync to a
device on both. macOS hasn't been tried yet, but the code doesn't do
anything platform-specific — device detection matches the Y1's folder
layout rather than any particular path, and file writes go through the
standard library rather than shelling out — so it's expected to work
there too. An issue reporting how it went (either way) is genuinely
useful if you're the first.

## Licence

MIT
