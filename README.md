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

```bash
uv tool install y1sync    # or: pipx install y1sync
```

For fingerprinting, install [chromaprint](https://acoustid.org/chromaprint)
and get a free [AcoustID API key](https://acoustid.org/new-application):

```toml
# ~/.config/y1sync/config.toml
acoustid_key = "your-key-here"
```

y1sync works without either — it falls back to filename lookup, and every
track then goes through review.

## Use

```bash
y1sync doctor              # check dependencies and find the device
y1sync scan ~/Music        # identify, tag and rename
y1sync sync ~/Music        # copy to the Y1
```

Add `--dry-run` to any command to see what would change without writing.

## Safety

`sync` is the only command that writes to the device. It refuses to write
unless the target carries the Y1 folder signature and is a FAT32 volume,
backs up before the first change, writes through a temporary file, and
flushes to disk before reporting success.

Backups go to `~/.local/share/y1sync/backups/`, never to the device.

## Licence

MIT
