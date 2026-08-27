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

## Install

Until the first PyPI release, install from source:

```bash
pip install git+https://github.com/lukamilicevic/y1sync
```

Once published, this becomes:

```bash
uv tool install y1sync    # or: pipx install y1sync
```

### Setting up fingerprinting

Fingerprinting is what makes y1sync accurate, and it needs two things.

**1. chromaprint**, which computes the fingerprint:

```bash
sudo apt install libchromaprint-tools    # Debian, Ubuntu
brew install chromaprint                 # macOS
```

**2. An AcoustID *application* key.**

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

## Licence

MIT
