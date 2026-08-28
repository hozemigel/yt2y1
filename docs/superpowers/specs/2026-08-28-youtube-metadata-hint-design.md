# YouTube metadata hint for identification

**Status:** approved for planning
**Date:** 2026-08-28

## Problem

`y1sync` identifies a track by audio fingerprint (fpcalc -> AcoustID ->
MusicBrainz). When the fingerprint returns nothing -- which is common for
obscure, independent, and electronic tracks that AcoustID has thin or no
coverage for -- it falls back to `guess_query_from_filename()` and an
iTunes search. That path is weak twice over: a YouTube-rip filename is
noisy, and iTunes has poor coverage for exactly the lesser-known material
the fingerprint also missed.

Meanwhile `yt2mp3` already receives everything yt-dlp extracted about the
video in `info_dict` -- `artist`, `track`, `album`, `release_year`,
`channel`, the "Provided to YouTube by" block parsed out of the
description -- and keeps only the path of the MP3 it wrote. For a track
from a YouTube Music "- Topic" channel or any video with a label-supplied
description, that metadata is clean and often exactly right.

## Goal

Carry yt-dlp's metadata from `yt2mp3` to `y1sync` and use it, in place of
the filename guess, to drive the non-fingerprint identification path --
so a lesser-known track that the fingerprint misses still lands a good
match, and the review prompt becomes one keypress instead of a puzzle.

## Non-goals

- Changing the fingerprint path. It always runs first and always wins
  when it returns anything.
- Auto-applying a hint-derived identification. Every candidate that is
  not fingerprint-confirmed still goes through review, and `--yes` still
  refuses it. This spec does not weaken that invariant.
- Embedding the metadata into ID3 tags at download time. `y1sync`'s
  premise is that existing tags are not to be trusted; a sidecar keeps
  the unverified data out of the tag space.
- Touching device sync or backup.

## Design

### Data flow

```
yt2mp3 download  ->  MP3 + <stem>.yt2mp3.json   (sidecar, same directory)
                                 |
y1sync scan  /  "Download from YouTube"
   identify(path):
     1. fingerprint route (fpcalc -> AcoustID -> MusicBrainz)   unchanged; wins if it returns anything
     2. fingerprint returned nothing  ->  load_hint(path)
          - MusicBrainz recording search by artist / track / album  (real release-group types)
          - synthesized candidate straight from the sidecar fields  (net for the genuinely obscure)
          - iTunes search seeded with "artist track" from the sidecar, not the filename
     3. every hint-derived candidate: source="youtube", confidence=0.0  ->  review, exactly as today
```

When no sidecar is present (a general library file, or `yt2mp3` was not
the source), `identify()` behaves exactly as it does today:
`guess_query_from_filename()` -> iTunes.

### Invariant preserved

`cli._is_a_guess()` is `candidate.source != "acoustid"`, and
`ranking.py` gates auto-accept on `top.source != "acoustid"` the same
way. A hint-derived candidate carries `source="youtube"`, so it is
automatically treated as a guess: routed to review, refused by `--yes`.
No change to either check is required.

### Component: `yt2mp3/src/yt2mp3/metadata.py` (new, ~40 lines)

`write_sidecar(info: dict, mp3_path: str | Path) -> None`

- Derives the sidecar path as `<mp3 stem>.yt2mp3.json` in the MP3's
  directory.
- Pulls from `info`: `artist`, `track`, `album`, `release_year` (fall
  back to `release_date[:4]`), `channel`, `title`, `webpage_url`.
- Writes only keys that are present and non-empty.
- If `artist` is a list, joins it with `", "`.
- Envelope carries `"schema": 1` and `"tool": "yt2mp3"` for
  forward-compatibility.
- Best-effort: any write failure is swallowed (a download that succeeded
  must not be reported as failed because a sidecar could not be written).

Example:

```json
{
  "schema": 1,
  "tool": "yt2mp3",
  "url": "https://www.youtube.com/watch?v=xxxxxxxxxxx",
  "video_title": "SZA - Snooze (Official Video)",
  "channel": "SZAVEVO",
  "artist": "SZA",
  "track": "Snooze",
  "album": "SOS",
  "year": "2022"
}
```

### Component: `yt2mp3/src/yt2mp3/downloader.py` (modified)

In the existing `_make_postprocessor_hook`, on the `status == "finished"`
event where `info.get("ext") == "mp3"` (the point that already has the
final `filepath`), call `write_sidecar(info, path)`.

This covers both the standalone `yt2mp3 <url>` CLI and the `y1sync`
"Download from YouTube" menu flow, since both go through `download()`.

No new flag. `--no-sidecar` is a possible later addition, out of scope
here.

### Component: `y1sync/src/y1sync/hint.py` (new, ~40 lines)

```python
@dataclass(frozen=True)
class YtHint:
    artist: str | None = None
    track: str | None = None
    album: str | None = None
    year: str | None = None
    video_title: str | None = None
    url: str | None = None

def load_hint(mp3_path: Path) -> YtHint | None: ...
```

- Looks for `<stem>.yt2mp3.json` next to `mp3_path`.
- Parses defensively: missing file, unreadable file, or malformed JSON
  all return `None` -- mirrors `cache.py`'s tolerance.
- Maps the sidecar keys onto `YtHint` fields. Unknown keys ignored.
- Returns `None` if the result has neither `artist` nor `track` nor
  `video_title` (nothing usable).

### Component: `y1sync/src/y1sync/identify.py` (modified)

`identify()` keeps its current signature (`path, api_key=None,
session=None`). It calls `load_hint(path)` internally at the top of the
fallback branch, so callers -- `cmd_scan` in particular -- do not change
and `y1sync scan` on a folder of downloads benefits with zero wiring.

New helper:

```python
def musicbrainz_recording_search(
    artist: str, track: str, album: str | None, session=None
) -> list[dict]:
    """Search MusicBrainz recordings by text. Returns recording dicts."""
```

- `GET /ws/2/recording?query=<lucene>&fmt=json` with the existing
  `MUSICBRAINZ_USER_AGENT` and a `MUSICBRAINZ_RATE_LIMIT` sleep.
- Lucene query: `recording:"<track>" AND artist:"<artist>"`, plus
  `AND release:"<album>"` when an album is known.
- Same defensive shape as `musicbrainz_releases()`: any exception or
  non-ok response -> `[]`.

Fallback branch, replacing the current filename-guess-only path:

```python
hint = load_hint(path)
candidates: list[Candidate] = []

if hint and (hint.artist or hint.track):
    recordings = musicbrainz_recording_search(
        hint.artist or "", hint.track or "", hint.album, http
    )
    for recording in recordings[:MAX_RECORDINGS_EXPANDED]:
        releases = musicbrainz_releases(recording["id"], http)
        candidates += candidates_from_musicbrainz(recording, releases, 0.0)
    # candidates_from_musicbrainz sets source="acoustid"; the hint path
    # must override that to source="youtube" (see below).

    # Synthesized candidate straight from the sidecar: the answer when
    # MusicBrainz also has nothing on an obscure track.
    candidates.append(Candidate(
        meta=TrackMeta(
            artist=hint.artist or "",
            title=hint.track or hint.video_title or "",
            album=hint.album or "",
            year=hint.year,
        ),
        confidence=0.0,
        source="youtube",
        release_group_type="Album",
        release_status="Official",
        release_date=None,   # sorts last among equals in ranking
    ))

    itunes_term = " ".join(t for t in (hint.artist, hint.track) if t)
else:
    itunes_term = guess_query_from_filename(path)

# existing iTunes search, now seeded from itunes_term, appended to candidates
```

The function returns `candidates` (MusicBrainz-from-hint + synthesized +
iTunes) instead of today's `return parse_itunes_response(...)`. When
there is no hint, `candidates` is empty going in and the result is
exactly today's iTunes-only list. `MAX_RECORDINGS_EXPANDED` is reused as
the cap on how many search recordings to expand; a dedicated constant is
fine too if the planner prefers.

`source` override: the cleanest option is a small parameter on
`candidates_from_musicbrainz(..., source="acoustid")` defaulting to the
current value, passed `"youtube"` from the hint path. `parse_itunes_response`
already stamps `source="itunes"`; those candidates stay as they are
(still guesses, still reviewed).

All hint-derived candidates therefore have `confidence=0.0` and
`source` in `{"youtube", "itunes"}` -- never `"acoustid"`.

### Component: `y1sync/src/y1sync/review.py` (modified)

In `choose_candidate`, when the top ranked candidate has
`source == "youtube"`, print one line before the options:

```
  From the YouTube page: SZA — Snooze (SOS, 2022)
```

Album and year shown only when present. Purely informational; does not
change what is selectable or the default.

### Ranking

`rank_candidates` does not consider `source`. The synthesized candidate
has `release_date=None`, which the existing `_NO_DATE` sentinel already
sorts to the bottom within an equal type band, so real MusicBrainz
releases with dates rank above the bare synthetic. No `ranking.py`
change.

### Caching

`ContentCache` keys on the audio content hash and stores
`candidates + choice`. Hint-derived candidates are cached like any
others. No change.

### Device sync

Sidecars live in the music library on the computer. `_find_mp3s()` globs
`*.mp3` only, and `cmd_sync` copies only what it returns, so `.yt2mp3.json`
files are never copied to the Y1. Device backup runs device -> computer
and does not see them either. `device.py` is not touched.

## Files

**New**
- `yt2mp3/src/yt2mp3/metadata.py`
- `y1sync/src/y1sync/hint.py`
- `yt2mp3/tests/test_metadata.py`
- `y1sync/tests/test_hint.py`

**Modified**
- `yt2mp3/src/yt2mp3/downloader.py` -- call `write_sidecar` in the mp3 postprocessor hook
- `y1sync/src/y1sync/identify.py` -- hint-aware fallback, `musicbrainz_recording_search`, `source` param on `candidates_from_musicbrainz`
- `y1sync/src/y1sync/review.py` -- "From the YouTube page:" line
- `y1sync/tests/test_identify.py` -- new cases
- `CHANGELOG.md` -- Unreleased entry
- `README.md`, `y1sync/README.md`, `yt2mp3/README.md` -- brief mention

**Not touched**
- `y1sync/src/y1sync/device.py`, `cache.py`, `ranking.py`, `naming.py`

## Testing

**`yt2mp3/tests/test_metadata.py`**
- fake `info_dict` -> expected JSON content
- missing fields are omitted, not written as null/empty
- `artist` as a list is joined with `", "`
- `year` falls back to `release_date[:4]` when `release_year` absent
- sidecar path is derived from the MP3 path (`<stem>.yt2mp3.json`, same dir)
- a write failure (unwritable dir) does not raise

**`y1sync/tests/test_hint.py`**
- well-formed sidecar parses to the right `YtHint`
- missing file -> `None`
- malformed JSON -> `None`
- sidecar with only `channel`/`url` (no artist/track/title) -> `None`

**`y1sync/tests/test_identify.py` (additions, stubbed `session`)**
- fingerprint returns nothing + hint present -> MusicBrainz recording
  search is called with the hint's artist/track; resulting candidates
  carry `source="youtube"`, `confidence=0.0`
- fingerprint returns nothing + hint present + MusicBrainz returns
  nothing -> the synthesized `source="youtube"` candidate is still
  returned
- no sidecar -> `guess_query_from_filename` + iTunes path runs exactly as
  before (existing tests remain green)
- iTunes search term is seeded from the hint when a hint is present

**`y1sync/tests/test_cli.py` (addition)**
- a `source="youtube"` pick is treated as a guess: under `--yes` it is
  refused and reported as needing review, not applied

## Risks

- yt-dlp only populates `artist`/`track`/`album` for music-ish videos.
  For an arbitrary video the sidecar is sparse (`title`/`channel`/`url`)
  and `load_hint` returns `None` or a hint with only `video_title`; the
  fallback then behaves close to today. Acceptable.
- One extra rate-limited MusicBrainz request per fingerprint-less track.
  The existing sleep mechanics cover it; the tracks that hit this path
  are a minority.
- Multi-artist / "feat." strings are passed to the MusicBrainz query
  as-is. The Lucene search is tolerant; not worth special handling in v1.
