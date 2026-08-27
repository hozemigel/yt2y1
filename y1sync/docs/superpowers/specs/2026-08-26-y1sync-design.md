# y1sync — Design

**Date:** 2026-08-26
**Status:** Approved for planning
**Author:** Luka Milicevic

## Problem

The Innioasis Y1 is a cheap Rockchip-based portable music player. Its
library screen groups tracks by ID3 tags and shows embedded cover art.
People load it with MP3s ripped from YouTube, and those files arrive with
no tags at all — so the device shows a flat list of filenames under
"Unknown Artist", with no artwork.

Fixing this by hand is tedious and error-prone. A manual pass over a
15-track library produced concrete evidence of where the errors come from:

| Track | What a filename-based lookup returned | Correct answer |
|---|---|---|
| Shaggy — Angel | 2020 re-recording feat. Sting | 2000 original, feat. Rayvon |
| Black — Wonderful Life | A different artist entirely (Matthew West) | BLACK, *Wonderful Life* (1986) |
| Fleetwood Mac — Dreams | *Greatest Hits* compilation | *Rumours* (1977) |
| The Cranberries — Ode To My Family | *Stars* compilation | *No Need To Argue* (1994) |

Four of fifteen tracks — roughly 27% — needed manual correction. Every
failure traces to the same root cause: the lookup guessed from the
filename, and the filename was YouTube debris such as
`Goo Goo Dolls - Iris (Live in Buffalo, NY, 7⧸4⧸2004) [Official Video].mp3`.

Existing tools do not close this gap. beets, MusicBrainz Picard and mp3tag
are mature and general, but none of them know what the Y1 needs: ID3v2.3
rather than v2.4, FAT32 filename limits, or the device's folder layout.

## Goals

- Identify tracks by the audio itself, not by the filename
- Write tags the Y1 actually reads, with embedded cover art
- Produce FAT32-safe filenames on every host OS
- Copy to the device without risking the user's data
- Be honest about uncertainty: apply what is certain, ask about the rest

## Non-goals

- Supporting other players. Y1 only. Device abstraction is deliberately absent.
- Competing with beets or Picard as a general-purpose tagger.
- Audio transcoding, format conversion, or gain analysis.
- Playlists, theme management and backup/restore. Deferred past v1.0.
- A GUI.

## Users

Y1 owners with a folder of untagged MP3s who are comfortable running a
command. They are not expected to know what ID3v2.3 or AcoustID are.

## Approach

A Python package installed as a CLI tool (`uv tool install y1sync` or
`pipx install y1sync`), exposing three subcommands.

Alternatives considered and rejected:

- **Single-file script.** Zero install friction, but untestable. For a tool
  that writes to removable media, untestability is disqualifying.
- **Library plus thin CLI.** Enables third-party GUIs, but nobody has asked
  for one. YAGNI. Module boundaries below leave the option open at no cost.

## Modules

Each module has one responsibility and is testable without a real device.

| Module | Responsibility |
|---|---|
| `models.py` | The `TrackMeta` and `Candidate` records shared across modules |
| `cli.py` | Subcommands, argument parsing, output formatting |
| `identify.py` | Answer "which recording is this?" — returns ranked candidates with confidence scores. Never decides. |
| `ranking.py` | Rank releases and apply the auto-versus-ask decision rules |
| `cache.py` | Cache identification results by audio content hash |
| `artwork.py` | Fetch and cache cover art |
| `tagging.py` | Write ID3v2.3 via mutagen |
| `naming.py` | Derive a FAT32-safe, cross-platform-safe filename |
| `device.py` | Locate and verify the Y1; perform safe copies. The only OS-aware module. |
| `review.py` | The needs-review queue and its prompts |
| `config.py` | Read `~/.config/y1sync/config.toml` — AcoustID API key, preferred artwork size, default music folder |

The critical boundary is that `identify.py` returns candidates and
confidence but never picks a winner. All decision logic lives in
`ranking.py` and is testable with no network access.

There is deliberately no separate `metadata.py`. Each identification
source builds a `TrackMeta` as it parses its own response, so a normalizing
layer between them would only forward data unchanged.

## Identification

Two sources, in order:

1. **Chromaprint fingerprint → AcoustID → MusicBrainz.** Fingerprints the
   decoded audio, so the filename is irrelevant. This is what resolves the
   Shaggy and Black failures above.
2. **Filename heuristic → iTunes Search API.** Fallback when chromaprint is
   unavailable or the fingerprint is unmatched.

Cover art comes from iTunes at 600×600 regardless of which source
identified the track. The Cover Art Archive is used as a fallback; its
coverage is uneven.

The tool remains functional with neither an AcoustID key nor chromaprint
installed. It degrades to source 2, and every track then goes through
review. `y1sync doctor` reports what is missing and how to install it.

## Decision rules

When a track is written automatically and when the user is asked:

- AcoustID score ≥ 0.90 **and** exactly one candidate release → apply automatically
- AcoustID score ≥ 0.90 **and** multiple releases → **ask**, ranking originals first
- No fingerprint match; filename heuristic only → **always ask**

Release ranking, applied when a recording appears on several releases:

1. Prefer release-group primary type `Album`
2. Exclude secondary types `Compilation`, `Live`, `Remix`, `DJ-mix` from the top rank
3. Prefer release status `Official`
4. Among survivors, prefer the earliest release date

This ranking is the encoded form of the *Rumours* and *No Need To Argue*
corrections. A fingerprint states which recording a file contains; it
cannot state which release the user wants it filed under. The tool ranks
the original first and lets the user confirm rather than guessing.

## Tagging

ID3v2.3, not v2.4 — older players including the Y1 read v2.3 reliably.

Text encoding is UTF-16, set explicitly. ID3v2.3 permits only ISO-8859-1
and UTF-16; UTF-8 is out of spec. mutagen silently downgrades a UTF-8
request when saving as v2.3, and the tool must not depend on that
incidental behavior.

Frames written: `TIT2`, `TPE1`, `TPE2`, `TALB`, `TYER`, `TCON`, `TRCK`, and
`APIC` (JPEG, cover front). `TPE2` is set to the track artist so the Y1
groups correctly.

`TYER` is used rather than `TDRC`: `TDRC` is a v2.4 frame, and mutagen maps
it to `TYER` when saving as v2.3. The tool sets `TYER` explicitly for the
same reason it sets the encoding explicitly — correctness must not rest on
a library's silent conversion.

Writing is idempotent: existing tags are cleared before the new set is
applied, so re-running never produces duplicate frames.

## Naming

Target format: `Artist - Title.mp3`, derived from the final tags so that
filename and tag can never disagree.

Sanitization, in order:

1. Map Unicode slash lookalikes to `-` — `⧸` (U+29F8), `⁄`, `∕`, `／`.
   These appear in YouTube rips because the real `/` is illegal in filenames.
2. Replace characters illegal on FAT32 and NTFS: `< > : " / \ | ? *` and control characters
3. Reject Windows reserved device names: `CON`, `PRN`, `AUX`, `NUL`,
   `COM1`–`COM9`, `LPT1`–`LPT9`. A track named "Aux" would otherwise produce
   a file Windows cannot open.
4. Collapse whitespace; strip leading and trailing dots and spaces
5. Truncate to 100 characters, leaving room for a disambiguating suffix
6. On collision, append ` (2)`, ` (3)`, …

**Case-only renames require a two-step rename through a temporary name.**
FAT32 is case-insensitive, so renaming `Black - X.mp3` to `BLACK - X.mp3`
is a no-op that a naive implementation silently skips. This was observed in
practice during the manual pass.

## Cross-platform behavior

Supported: Linux, macOS, Windows. `device.py` is the only module that
varies.

| OS | Mount discovery |
|---|---|
| Linux | `/media/$USER/`, `/run/media/$USER/`, `/proc/mounts` |
| macOS | `/Volumes/` |
| Windows | Drive letters |

Enumeration uses `psutil.disk_partitions()`, which is uniform across all
three. Device *recognition* is fully portable: it matches the Y1's folder
signature — `Music/`, `Themes/`, `Audiobooks/`, `Videos/` — rather than any
path, so the same code and the same tests apply everywhere.

Durability uses `os.fsync()` per file. The Unix-only `os.sync()` is not
used: per-file fsync works on all three platforms and guarantees the
specific file rather than something global.

## Write safety

`sync` is the only command that writes to removable media, and it is
deliberately defensive:

1. Refuse to write unless the target matches the Y1 folder signature
2. Refuse to write unless the filesystem is FAT32
3. Back up before the first modification, to
   `~/.local/share/y1sync/backups/<device-label>/<timestamp>/`. Backups are
   never written to the device itself, which may be full or failing.
4. Write to a temporary file, then rename — an interruption leaves the old
   file intact rather than a half-written new one
5. `os.fsync()` before reporting success
6. `--dry-run` on every mutating command

## Caching

Identification results are cached in `~/.cache/y1sync/`, keyed by a hash of
the file's audio content. Re-running on the same folder neither re-queries
the network nor re-asks questions already answered. This matters because
the expected usage is repeated runs on a growing folder.

## CLI surface

```
y1sync doctor              # report missing dependencies and device status
y1sync scan <folder>       # identify, tag and rename in place
y1sync sync <folder>       # copy a prepared folder to the device
```

Global flags:

- `--dry-run` — report what would change; write nothing
- `--yes` — accept the top-ranked candidate for every track that would
  otherwise be queued for review, and proceed without confirmation prompts.
  Intended for scripted runs. Because it suppresses exactly the judgement
  that catches compilation-versus-original mistakes, `scan --yes` prints a
  summary of every auto-accepted ambiguous track so the choices remain
  auditable.
- `--verbose` — per-track detail including confidence scores

## Testing

Everything except final hardware validation runs without a device.

- `naming.py`, `tagging.py` — unit tests covering every ugly case observed
  in practice: `⧸`, `(Official Video)`, the `Black`/`BLACK` case-only
  rename, `CON.mp3`
- `identify.py` — recorded HTTP fixtures, no live network. **The four
  real-world failures become permanent regression tests.**
- `device.py` — a temporary directory containing the Y1 folder signature
  stands in for the device
- CI — GitHub Actions, matrix across Linux, macOS and Windows

Local development is Linux-only; macOS and Windows behavior is verified
solely by CI.

## Repository

- License: MIT
- `README.md` — what it does, install, the three commands, a screenshot of output
- `CONTRIBUTING.md`, issue templates
- Packaged with `pyproject.toml`; published to PyPI as `y1sync`

## Deferred

Playlist generation, theme management, backup/restore as a user-facing
command, and support for other players. None are in v1.0.
