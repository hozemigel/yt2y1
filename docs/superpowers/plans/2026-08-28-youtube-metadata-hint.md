# YouTube metadata hint for identification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an audio fingerprint returns nothing, identify a track from
the metadata YouTube gave `yt2mp3` (carried in a sidecar JSON file)
instead of guessing from the filename.

**Architecture:** `yt2mp3` writes `<stem>.yt2mp3.json` next to every MP3 it
produces, built from yt-dlp's `info_dict`. `y1sync`'s `identify()` reads
that sidecar on its non-fingerprint path and uses it to (a) text-search
MusicBrainz for real releases, (b) synthesize a fallback candidate
directly from the sidecar, and (c) seed the existing iTunes search.
Every hint-derived candidate carries `source="youtube"`, so it stays
behind review exactly as filename guesses do today.

**Tech Stack:** Python 3.10+, `pytest`, `requests` (y1sync), `yt-dlp`
(yt2mp3). Two separate packages under one repo: `yt2mp3/` and `y1sync/`,
each with `src/` layout and its own `tests/`.

**Spec:** `docs/superpowers/specs/2026-08-28-youtube-metadata-hint-design.md`

## Global Constraints

- **Fingerprint path is never changed.** It runs first and its result
  wins whenever it returns any candidate. This plan only touches the
  branch reached when it returns nothing.
- **No hint-derived candidate is `source="acoustid"`.** They are all
  `source="youtube"` (or `"itunes"` from the existing iTunes parse), with
  `confidence=0.0`. `cli._is_a_guess()` is `candidate.source != "acoustid"`
  and `ranking.decide()` gates auto-accept on `top.source != "acoustid"`;
  both must keep treating hint candidates as guesses with no code change.
- **`write_sidecar()` never raises.** A download that succeeded must not
  be reported as failed because a sidecar could not be written.
- **`load_hint()` never raises.** Missing file, unreadable file, or
  malformed JSON all mean "no hint"; `identify()` then behaves exactly as
  it does today.
- **No new runtime dependencies** in either package.
- Sidecar filename suffix is exactly `.yt2mp3.json`. Envelope carries
  `"schema": 1` and `"tool": "yt2mp3"`.
- Follow existing code style: module docstring explaining *why*, terse
  comments only where a decision is non-obvious, `snake_case`, type hints
  on public functions.
- Run a package's tests from its own directory: `cd yt2mp3 && python -m
  pytest` or `cd y1sync && python -m pytest`.
- Commit messages: imperative mood, `feat:` / `test:` / `docs:` prefix as
  the repo already uses. **Do not add any AI-attribution trailer** — a
  repo hook rejects commits (and the command itself) that carry
  `Co-Authored-By` an AI, `Generated with…`, or a session link.

---

### Task 1: `yt2mp3` sidecar writer

**Files:**
- Create: `yt2mp3/src/yt2mp3/metadata.py`
- Test: `yt2mp3/tests/test_metadata.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `SIDECAR_SUFFIX: str` == `".yt2mp3.json"`
  - `SCHEMA_VERSION: int` == `1`
  - `sidecar_path(mp3_path: str | Path) -> Path` — the sidecar location
    for a given MP3: same directory, stem + `SIDECAR_SUFFIX`.
  - `build_sidecar(info: dict) -> dict` — the JSON body; keys whose value
    is missing/empty are omitted; always contains `schema` and `tool`.
  - `write_sidecar(info: dict, mp3_path: str | Path) -> None` — writes
    `build_sidecar(info)` to `sidecar_path(mp3_path)`; swallows `OSError`.

- [ ] **Step 1: Write the failing tests**

Create `yt2mp3/tests/test_metadata.py`:

```python
import json
from pathlib import Path

from yt2mp3.metadata import (
    SCHEMA_VERSION,
    SIDECAR_SUFFIX,
    build_sidecar,
    sidecar_path,
    write_sidecar,
)


def test_sidecar_path_sits_next_to_the_mp3():
    assert sidecar_path("/music/Artist/Song.mp3") == Path(
        "/music/Artist/Song.yt2mp3.json"
    )
    assert SIDECAR_SUFFIX == ".yt2mp3.json"


def test_build_sidecar_keeps_the_known_fields():
    body = build_sidecar({
        "webpage_url": "https://youtu.be/abc",
        "title": "SZA - Snooze (Official Video)",
        "channel": "SZAVEVO",
        "artist": "SZA",
        "track": "Snooze",
        "album": "SOS",
        "release_year": "2022",
    })
    assert body == {
        "schema": SCHEMA_VERSION,
        "tool": "yt2mp3",
        "url": "https://youtu.be/abc",
        "video_title": "SZA - Snooze (Official Video)",
        "channel": "SZAVEVO",
        "artist": "SZA",
        "track": "Snooze",
        "album": "SOS",
        "year": "2022",
    }


def test_build_sidecar_omits_missing_and_empty_fields():
    body = build_sidecar({"title": "Just A Video", "artist": "", "album": None})
    assert body == {"schema": 1, "tool": "yt2mp3", "video_title": "Just A Video"}
    assert "artist" not in body and "album" not in body


def test_build_sidecar_joins_a_list_of_artists():
    body = build_sidecar({"artist": ["Calvin Harris", "Dua Lipa"], "track": "x"})
    assert body["artist"] == "Calvin Harris, Dua Lipa"


def test_build_sidecar_falls_back_to_release_date_for_the_year():
    body = build_sidecar({"track": "x", "release_date": "20191108"})
    assert body["year"] == "2019"


def test_build_sidecar_prefers_uploader_when_channel_is_absent():
    body = build_sidecar({"track": "x", "uploader": "Some Label"})
    assert body["channel"] == "Some Label"


def test_write_sidecar_writes_parseable_json(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    write_sidecar({"artist": "A", "track": "B"}, mp3)
    body = json.loads((tmp_path / "Song.yt2mp3.json").read_text(encoding="utf-8"))
    assert body["artist"] == "A"
    assert body["track"] == "B"


def test_write_sidecar_swallows_a_write_failure(tmp_path):
    # Parent directory does not exist -> OSError -> must not propagate.
    missing = tmp_path / "no-such-dir" / "Song.mp3"
    write_sidecar({"artist": "A"}, missing)  # no exception
    assert not (tmp_path / "no-such-dir").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd yt2mp3 && python -m pytest tests/test_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'yt2mp3.metadata'`

- [ ] **Step 3: Write the implementation**

Create `yt2mp3/src/yt2mp3/metadata.py`:

```python
"""Write a sidecar recording what YouTube said a download was.

yt-dlp hands ``download()`` a fully populated ``info_dict`` -- artist,
track, album, release year, the "Provided to YouTube by" block parsed out
of the description -- and yt2mp3 otherwise keeps only the path of the MP3
it wrote. For a track from a YouTube Music "- Topic" channel that
metadata is usually clean and often exactly right, and it is precisely
what y1sync needs when an audio fingerprint comes back empty (obscure and
independent tracks, mostly). This drops it beside the MP3 as
``<stem>.yt2mp3.json`` for y1sync to pick up; y1sync ignores files it
cannot read or parse, so a partial or missing sidecar costs nothing.
"""

import json
from pathlib import Path

SIDECAR_SUFFIX = ".yt2mp3.json"
SCHEMA_VERSION = 1


def sidecar_path(mp3_path: str | Path) -> Path:
    """Where the sidecar for a given MP3 lives: beside it, same stem."""
    mp3 = Path(mp3_path)
    return mp3.with_name(mp3.stem + SIDECAR_SUFFIX)


def _clean(value) -> str | None:
    """A trimmed non-empty string, or None. A list/tuple joins on ", "."""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v).strip() for v in value if str(v).strip())
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_sidecar(info: dict) -> dict:
    """The JSON body for one download's sidecar. Empty fields are omitted;
    ``schema`` and ``tool`` are always present."""
    year = _clean(info.get("release_year"))
    if not year:
        release_date = _clean(info.get("release_date"))  # yt-dlp gives "YYYYMMDD"
        year = release_date[:4] if release_date else None

    fields = {
        "url": _clean(info.get("webpage_url")),
        "video_title": _clean(info.get("title")),
        "channel": _clean(info.get("channel") or info.get("uploader")),
        "artist": _clean(info.get("artist")),
        "track": _clean(info.get("track")),
        "album": _clean(info.get("album")),
        "year": year,
    }
    body = {"schema": SCHEMA_VERSION, "tool": "yt2mp3"}
    body.update({key: value for key, value in fields.items() if value is not None})
    return body


def write_sidecar(info: dict, mp3_path: str | Path) -> None:
    """Write the sidecar for a finished download. Never raises: a sidecar
    that could not be written must not turn a successful download into a
    reported failure -- y1sync just falls back to its filename guess."""
    try:
        sidecar_path(mp3_path).write_text(
            json.dumps(build_sidecar(info), ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd yt2mp3 && python -m pytest tests/test_metadata.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add yt2mp3/src/yt2mp3/metadata.py yt2mp3/tests/test_metadata.py
git commit -m "feat: write a sidecar of yt-dlp's metadata beside each MP3"
```

---

### Task 2: Wire the sidecar into the download hook

**Files:**
- Modify: `yt2mp3/src/yt2mp3/downloader.py` (`_make_postprocessor_hook`, imports)
- Test: `yt2mp3/tests/test_downloader.py` (add two tests)

**Interfaces:**
- Consumes: `metadata.write_sidecar`, `metadata.sidecar_path` (Task 1).
- Produces: no new symbols. After `download()` finishes an MP3, a
  `<stem>.yt2mp3.json` exists beside it.

- [ ] **Step 1: Write the failing tests**

Add to `yt2mp3/tests/test_downloader.py` (it already imports
`DownloadOptions, build_ydl_opts, download` and
`yt2mp3.downloader as downloader_module`; add `import json`):

```python
def test_download_writes_a_sidecar_next_to_the_mp3(monkeypatch, tmp_path):
    mp3 = tmp_path / "Song.mp3"

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {
                    "ext": "mp3", "filepath": str(mp3),
                    "title": "SZA - Snooze", "artist": "SZA", "track": "Snooze",
                    "album": "SOS", "release_year": "2022", "channel": "SZAVEVO",
                    "webpage_url": "https://youtu.be/x",
                }})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    from yt2mp3.metadata import sidecar_path
    download(DownloadOptions(url="https://youtu.be/x", output_dir=str(tmp_path)))

    body = json.loads(sidecar_path(mp3).read_text(encoding="utf-8"))
    assert body["artist"] == "SZA"
    assert body["track"] == "Snooze"
    assert body["year"] == "2022"


def test_a_sidecar_write_failure_does_not_break_the_download(monkeypatch):
    # filepath points into a directory that does not exist: write_sidecar
    # swallows the OSError, and the download still reports success and
    # still records the path for its caller.
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {
                    "ext": "mp3", "filepath": "/no/such/dir/Song.mp3",
                }})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    collected: list[str] = []
    rc = download(DownloadOptions(url="https://youtu.be/x"), collected)

    assert rc == 0
    assert collected == ["/no/such/dir/Song.mp3"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd yt2mp3 && python -m pytest tests/test_downloader.py -v`
Expected: `test_download_writes_a_sidecar_next_to_the_mp3` FAILS
(`FileNotFoundError` on `sidecar_path(mp3).read_text()` — no sidecar
written). The other new test passes only by luck; both must be green
after Step 3.

- [ ] **Step 3: Write the implementation**

In `yt2mp3/src/yt2mp3/downloader.py`, add the import near the top with the
other package import:

```python
from .metadata import write_sidecar
```

In `_make_postprocessor_hook`, inside `hook(d)`, the block currently reads:

```python
            path = info.get("filepath") or info.get("_filename", "")
            print(f"Saved: {path}")
            if downloaded_files is not None:
                downloaded_files.append(path)
```

Change it to:

```python
            path = info.get("filepath") or info.get("_filename", "")
            print(f"Saved: {path}")
            if path:
                # What YouTube said this track was, for y1sync to use when
                # a fingerprint later comes back empty. Best-effort by
                # contract -- see metadata.write_sidecar.
                write_sidecar(info, path)
            if downloaded_files is not None:
                downloaded_files.append(path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd yt2mp3 && python -m pytest -v`
Expected: PASS (whole yt2mp3 suite green, including the pre-existing
`test_downloaded_files_*` tests)

- [ ] **Step 5: Commit**

```bash
git add yt2mp3/src/yt2mp3/downloader.py yt2mp3/tests/test_downloader.py
git commit -m "feat: write the metadata sidecar as each download finishes"
```

---

### Task 3: `y1sync` hint loader

**Files:**
- Create: `y1sync/src/y1sync/hint.py`
- Test: `y1sync/tests/test_hint.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `YtHint` — frozen dataclass, fields `artist, track, album, year,
    video_title, url`, each `str | None = None`; property `usable -> bool`
    (`True` when any of `artist`, `track`, `video_title` is set).
  - `load_hint(mp3_path: Path) -> YtHint | None` — reads
    `<stem>.yt2mp3.json` beside the MP3; returns `None` for a missing,
    unreadable, non-object, malformed, or not-`usable` sidecar.

- [ ] **Step 1: Write the failing tests**

Create `y1sync/tests/test_hint.py`:

```python
import json
from pathlib import Path

from y1sync.hint import YtHint, load_hint


def _write(mp3: Path, body) -> None:
    mp3.with_name(mp3.stem + ".yt2mp3.json").write_text(
        json.dumps(body), encoding="utf-8"
    )


def test_loads_a_well_formed_sidecar(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    _write(mp3, {
        "schema": 1, "tool": "yt2mp3", "url": "https://youtu.be/x",
        "video_title": "SZA - Snooze (Official Video)", "channel": "SZAVEVO",
        "artist": "SZA", "track": "Snooze", "album": "SOS", "year": "2022",
    })
    hint = load_hint(mp3)
    assert hint == YtHint(
        artist="SZA", track="Snooze", album="SOS", year="2022",
        video_title="SZA - Snooze (Official Video)", url="https://youtu.be/x",
    )
    assert hint.usable is True


def test_no_sidecar_is_no_hint(tmp_path):
    assert load_hint(tmp_path / "Song.mp3") is None


def test_malformed_json_is_no_hint(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    mp3.with_name("Song.yt2mp3.json").write_text("{not json", encoding="utf-8")
    assert load_hint(mp3) is None


def test_a_json_array_is_no_hint(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    mp3.with_name("Song.yt2mp3.json").write_text("[]", encoding="utf-8")
    assert load_hint(mp3) is None


def test_a_sidecar_with_nothing_to_search_on_is_no_hint(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    _write(mp3, {"schema": 1, "tool": "yt2mp3", "channel": "X",
                 "url": "https://youtu.be/x"})
    assert load_hint(mp3) is None


def test_blank_strings_are_dropped(tmp_path):
    mp3 = tmp_path / "Song.mp3"
    _write(mp3, {"artist": "   ", "track": "Snooze", "album": ""})
    hint = load_hint(mp3)
    assert hint.artist is None
    assert hint.track == "Snooze"
    assert hint.album is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd y1sync && python -m pytest tests/test_hint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'y1sync.hint'`

- [ ] **Step 3: Write the implementation**

Create `y1sync/src/y1sync/hint.py`:

```python
"""Load the sidecar yt2mp3 leaves next to a download.

When an audio fingerprint comes back empty, identify() would otherwise
guess from the filename. If yt2mp3 fetched the file it also wrote what
YouTube said the track was (see yt2mp3/metadata.py), and for the
lesser-known tracks a fingerprint tends to miss that is a far better
starting point. This reads that sidecar defensively: anything unreadable,
malformed, or with nothing to search on is simply "no hint", and
identify() carries on exactly as before.
"""

import json
from dataclasses import dataclass
from pathlib import Path

SIDECAR_SUFFIX = ".yt2mp3.json"


@dataclass(frozen=True)
class YtHint:
    """What YouTube said a track was. Every field is optional."""

    artist: str | None = None
    track: str | None = None
    album: str | None = None
    year: str | None = None
    video_title: str | None = None
    url: str | None = None

    @property
    def usable(self) -> bool:
        """True when there is something to search on rather than nothing."""
        return bool(self.artist or self.track or self.video_title)


def _sidecar_for(mp3_path: Path) -> Path:
    mp3 = Path(mp3_path)
    return mp3.with_name(mp3.stem + SIDECAR_SUFFIX)


def load_hint(mp3_path: Path) -> YtHint | None:
    """The YtHint for an MP3, or None when there is no usable sidecar."""
    try:
        raw = json.loads(_sidecar_for(mp3_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    def field(name: str) -> str | None:
        value = raw.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    hint = YtHint(
        artist=field("artist"),
        track=field("track"),
        album=field("album"),
        year=field("year"),
        video_title=field("video_title"),
        url=field("url"),
    )
    return hint if hint.usable else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd y1sync && python -m pytest tests/test_hint.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add y1sync/src/y1sync/hint.py y1sync/tests/test_hint.py
git commit -m "feat: read the yt2mp3 metadata sidecar into a YtHint"
```

---

### Task 4: `identify.py` helpers — `source` override and MusicBrainz search

**Files:**
- Modify: `y1sync/src/y1sync/identify.py`
  - `candidates_from_musicbrainz` — add a `source` parameter
  - add `musicbrainz_recording_search` and `_lucene_escape`
- Test: `y1sync/tests/test_identify.py` (add tests)

**Interfaces:**
- Consumes: existing `MUSICBRAINZ_ENDPOINT`, `MUSICBRAINZ_USER_AGENT`,
  `TIMEOUT`, `re`, `requests` in `identify.py`.
- Produces:
  - `candidates_from_musicbrainz(recording: dict, releases: list[dict],
    score: float, source: str = "acoustid") -> list[Candidate]` — the
    only change is that `Candidate.source` is now `source` instead of the
    hardcoded `"acoustid"`. All existing call sites keep the default.
  - `musicbrainz_recording_search(artist: str, track: str, album: str |
    None = None, session=None) -> list[dict]` — text search; returns
    recording dicts **normalised to the AcoustID recording shape**:
    `{"id": str, "title": str, "artists": [{"name": str}], "duration":
    float | None}` (`duration` in seconds). Any failure (exception,
    non-ok response, unparseable body, no `id`) yields `[]` or drops the
    row. Feeds straight into `musicbrainz_releases` +
    `candidates_from_musicbrainz`.

- [ ] **Step 1: Write the failing tests**

Add to `y1sync/tests/test_identify.py`. It already defines
`RoutingSession` (whose `.get` accepts `headers=None`) and imports from
`y1sync.identify`; extend the import line to add
`candidates_from_musicbrainz` and `musicbrainz_recording_search`.

```python
def test_candidates_from_musicbrainz_can_be_marked_a_non_fingerprint_source():
    from y1sync.identify import candidates_from_musicbrainz

    recording = {"title": "Snooze", "artists": [{"name": "SZA"}], "duration": 202.0}
    releases = [{
        "title": "SOS", "date": "2022-12-09", "status": "Official",
        "release-group": {"primary-type": "Album", "secondary-types": []},
    }]
    cands = candidates_from_musicbrainz(recording, releases, 0.0, source="youtube")
    assert cands and all(c.source == "youtube" for c in cands)
    assert cands[0].meta.album == "SOS"
    # Default is unchanged.
    assert candidates_from_musicbrainz(recording, releases, 0.9)[0].source == "acoustid"


def test_recording_search_builds_a_lucene_query_and_normalises_results():
    from y1sync.identify import MUSICBRAINZ_ENDPOINT, musicbrainz_recording_search

    captured = {}

    class SpySession:
        ok = True

        def get(self, url, params=None, timeout=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            session = self

            class Response:
                ok = True

                @staticmethod
                def json():
                    return {"recordings": [{
                        "id": "rec-1", "title": "Snooze", "length": 202000,
                        "artist-credit": [{"name": "SZA"}],
                    }, {
                        "id": None, "title": "dropped", "artist-credit": [],
                    }]}

            return Response()

    out = musicbrainz_recording_search("SZA", "Snooze", "SOS", SpySession())

    assert captured["url"] == MUSICBRAINZ_ENDPOINT
    assert captured["params"]["fmt"] == "json"
    query = captured["params"]["query"]
    assert 'recording:"Snooze"' in query
    assert 'artist:"SZA"' in query
    assert 'release:"SOS"' in query
    assert "User-Agent" in captured["headers"]
    # Normalised to the AcoustID recording shape; the row with no id is gone.
    assert out == [{
        "id": "rec-1", "title": "Snooze",
        "artists": [{"name": "SZA"}], "duration": 202.0,
    }]


def test_recording_search_returns_empty_on_a_failed_request():
    from y1sync.identify import musicbrainz_recording_search

    class DownSession:
        def get(self, url, params=None, timeout=None, headers=None):
            class Response:
                ok = False

                @staticmethod
                def json():
                    return {}

            return Response()

    assert musicbrainz_recording_search("A", "B", None, DownSession()) == []


def test_recording_search_needs_at_least_one_term():
    from y1sync.identify import musicbrainz_recording_search

    assert musicbrainz_recording_search("", "", None, object()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd y1sync && python -m pytest tests/test_identify.py -k "recording_search or non_fingerprint_source" -v`
Expected: FAIL — `ImportError` for `musicbrainz_recording_search`, and
`candidates_from_musicbrainz` has no `source` keyword.

- [ ] **Step 3: Write the implementation**

In `y1sync/src/y1sync/identify.py`:

**(a)** Change `candidates_from_musicbrainz`'s signature and the one
`source=` line inside it:

```python
def candidates_from_musicbrainz(
    recording: dict, releases: list[dict], score: float, source: str = "acoustid"
) -> list[Candidate]:
    """Build one candidate per release of a recording.

    ``source`` is "acoustid" for the fingerprint path and "youtube" when
    the recording came from a text search seeded by the YouTube sidecar;
    it must never be "acoustid" for the latter, or a guess would be
    eligible for automatic tagging.
    """
```

and, in the `Candidate(...)` built in its loop, replace
`source="acoustid",` with `source=source,`.

**(b)** Add, next to `musicbrainz_releases`:

```python
def _lucene_escape(text: str) -> str:
    """Neutralise the Lucene metacharacters a title or artist name carries."""
    return re.sub(r'(["\\])', r"\\\1", text)


def musicbrainz_recording_search(
    artist: str, track: str, album: str | None = None, session=None
) -> list[dict]:
    """Text-search MusicBrainz recordings, seeded from the YouTube sidecar.

    Used only on the no-fingerprint path. The result is normalised to the
    same shape an AcoustID hit's recording dict has -- ``artists`` a list
    of ``{"name": ...}``, ``duration`` in seconds -- so it can go straight
    into musicbrainz_releases() + candidates_from_musicbrainz(). Any
    failure yields [] and identify() falls through to its iTunes guess.
    """
    http = session or requests
    terms = []
    if track:
        terms.append(f'recording:"{_lucene_escape(track)}"')
    if artist:
        terms.append(f'artist:"{_lucene_escape(artist)}"')
    if album:
        terms.append(f'release:"{_lucene_escape(album)}"')
    if not terms:
        return []

    try:
        response = http.get(
            MUSICBRAINZ_ENDPOINT,
            params={"query": " AND ".join(terms), "fmt": "json", "limit": 5},
            headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
            timeout=TIMEOUT,
        )
    except Exception:
        return []
    if not getattr(response, "ok", False):
        return []
    try:
        found = response.json().get("recordings") or []
    except ValueError:
        return []

    normalised = []
    for rec in found:
        credit = rec.get("artist-credit") or []
        name = ""
        if credit:
            name = credit[0].get("name") or (credit[0].get("artist") or {}).get("name", "")
        length = rec.get("length")
        normalised.append({
            "id": rec.get("id"),
            "title": rec.get("title", ""),
            "artists": [{"name": name}],
            "duration": length / 1000.0 if isinstance(length, (int, float)) else None,
        })
    return [rec for rec in normalised if rec["id"]]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd y1sync && python -m pytest tests/test_identify.py -v`
Expected: PASS — the four new tests and every pre-existing test
(`candidates_from_musicbrainz`'s default keeps `source="acoustid"`).

- [ ] **Step 5: Commit**

```bash
git add y1sync/src/y1sync/identify.py y1sync/tests/test_identify.py
git commit -m "feat: add a MusicBrainz recording text search and a candidate source override"
```

---

### Task 5: `identify.py` — hint-aware fallback

**Files:**
- Modify: `y1sync/src/y1sync/identify.py`
  - `identify()` — its non-fingerprint tail becomes a call to `_fallback`
  - add `_fallback` and `_synthetic_candidate`
  - add `from .hint import load_hint` and `from .models import TrackMeta`
    (import `TrackMeta` if not already imported — it currently imports
    `Candidate, TrackMeta` from `.models`, so it is)
- Test: `y1sync/tests/test_identify.py`

**Interfaces:**
- Consumes: `hint.load_hint` (Task 3); `musicbrainz_recording_search`,
  `candidates_from_musicbrainz` with `source=`, `musicbrainz_releases`,
  `MAX_RECORDINGS_EXPANDED`, `MUSICBRAINZ_RATE_LIMIT`, `time`,
  `ITUNES_ENDPOINT`, `parse_itunes_response`, `guess_query_from_filename`
  (all already in `identify.py`).
- Produces:
  - `identify(path, api_key=None, session=None)` — **signature
    unchanged**. When the fingerprint path yields nothing it now returns
    `_fallback(path, http)`.
  - `_fallback(path: Path, http) -> list[Candidate]` — hint path when a
    usable sidecar sits beside `path`, filename path otherwise; the
    returned list mixes `source="youtube"` and `source="itunes"`
    candidates, never `"acoustid"`, all `confidence=0.0`.
  - `_synthetic_candidate(hint: YtHint) -> Candidate` —
    `source="youtube"`, `confidence=0.0`, `release_group_type="Album"`,
    `release_status="Official"`, `release_date=None` (sorts below any
    real dated release), `meta` from the hint (`title` falls back to
    `video_title`).

- [ ] **Step 1: Write the failing tests**

Add to `y1sync/tests/test_identify.py`. These write a real sidecar beside
a `tmp_path` MP3 so `load_hint` finds it, and set
`MAX_RECORDINGS_EXPANDED` to 1 so no `time.sleep` runs.

```python
import json as _json


def _sidecar(mp3, body):
    mp3.with_name(mp3.stem + ".yt2mp3.json").write_text(
        _json.dumps(body), encoding="utf-8"
    )


HINT_RECORDING_SEARCH = {"recordings": [
    {"id": "rec-snooze", "title": "Snooze", "length": 202000,
     "artist-credit": [{"name": "SZA"}]},
]}
HINT_RELEASES = {"releases": [{
    "title": "SOS", "date": "2022-12-09", "status": "Official",
    "release-group": {"primary-type": "Album", "secondary-types": []},
}]}


def test_the_hint_drives_the_fallback_when_there_is_no_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: None)
    monkeypatch.setattr("y1sync.identify.MAX_RECORDINGS_EXPANDED", 1)
    mp3 = tmp_path / "snooze rip.mp3"
    mp3.write_bytes(b"x")
    _sidecar(mp3, {"artist": "SZA", "track": "Snooze", "album": "SOS", "year": "2022"})

    session = RoutingSession({
        MUSICBRAINZ_ENDPOINT: HINT_RECORDING_SEARCH,
        f"{MUSICBRAINZ_ENDPOINT}/rec-snooze": HINT_RELEASES,
        ITUNES_ENDPOINT: {"results": []},
    })

    found = identify(mp3, session=session)

    assert MUSICBRAINZ_ENDPOINT in session.calls           # search was run
    assert f"{MUSICBRAINZ_ENDPOINT}/rec-snooze" in session.calls
    assert any(c.meta.album == "SOS" and c.source == "youtube" for c in found)
    assert all(c.source != "acoustid" for c in found)


def test_a_synthesized_candidate_survives_when_musicbrainz_has_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: None)
    mp3 = tmp_path / "obscure.mp3"
    mp3.write_bytes(b"x")
    _sidecar(mp3, {"artist": "Some DIY Act", "track": "Basement Tape", "year": "2013"})

    session = RoutingSession({
        MUSICBRAINZ_ENDPOINT: {"recordings": []},
        ITUNES_ENDPOINT: {"results": []},
    })

    found = identify(mp3, session=session)

    synth = [c for c in found if c.source == "youtube"]
    assert len(synth) == 1
    assert synth[0].meta.artist == "Some DIY Act"
    assert synth[0].meta.title == "Basement Tape"
    assert synth[0].meta.year == "2013"
    assert synth[0].release_date is None


def test_no_sidecar_keeps_the_filename_path_exactly(tmp_path, monkeypatch):
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: None)
    mp3 = tmp_path / "Shaggy - Angel.mp3"
    mp3.write_bytes(b"x")

    session = RoutingSession({ITUNES_ENDPOINT: SHAGGY_ITUNES})

    found = identify(mp3, session=session)

    assert MUSICBRAINZ_ENDPOINT not in session.calls
    assert session.calls == [ITUNES_ENDPOINT]
    assert [c.source for c in found] == ["itunes"]


def test_the_itunes_query_is_seeded_from_the_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: None)
    mp3 = tmp_path / "whatever noise (Official Audio).mp3"
    mp3.write_bytes(b"x")
    _sidecar(mp3, {"artist": "SZA", "track": "Snooze"})

    seen = {}

    class ParamSpy(RoutingSession):
        def get(self, url, params=None, timeout=None, headers=None):
            if url == ITUNES_ENDPOINT:
                seen["term"] = params["term"]
            return super().get(url, params, timeout, headers)

    session = ParamSpy({
        MUSICBRAINZ_ENDPOINT: {"recordings": []},
        ITUNES_ENDPOINT: {"results": []},
    })

    identify(mp3, session=session)

    assert seen["term"] == "SZA Snooze"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd y1sync && python -m pytest tests/test_identify.py -k "hint or synthesized or seeded_from_the_hint or filename_path_exactly" -v`
Expected: FAIL — `identify()` still runs the old filename-only tail, so
the MusicBrainz search is never called and no `source="youtube"`
candidate appears.

- [ ] **Step 3: Write the implementation**

In `y1sync/src/y1sync/identify.py`:

**(a)** Add near the top imports:

```python
from .hint import YtHint, load_hint
```

**(b)** Replace the tail of `identify()`. It currently ends with:

```python
    response = http.get(ITUNES_ENDPOINT, params={
        "term": guess_query_from_filename(path), "entity": "song", "limit": 5,
    }, timeout=TIMEOUT)
    if not response.ok:
        return []
    return parse_itunes_response(response.json())
```

Replace those lines with:

```python
    return _fallback(path, http)


def _synthetic_candidate(hint: YtHint) -> Candidate:
    """A candidate built straight from the sidecar -- the answer when
    MusicBrainz has nothing catalogued for an obscure track. release_date
    is left None so any real dated release ranks above it, and the source
    is "youtube" so it is always routed through review.
    """
    return Candidate(
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
        release_date=None,
    )


def _fallback(path: Path, http) -> list[Candidate]:
    """Identify without a fingerprint.

    From the YouTube sidecar when one sits beside the file -- a
    MusicBrainz text search for real releases, plus a candidate
    synthesized straight from the sidecar, plus the existing iTunes
    search seeded with the sidecar's artist and title. From the filename
    otherwise, exactly as before. Nothing here is source "acoustid", so
    every result goes through review.
    """
    hint = load_hint(path)
    candidates: list[Candidate] = []
    itunes_term = ""

    if hint is not None:
        recordings = musicbrainz_recording_search(
            hint.artist or "", hint.track or "", hint.album, http
        )
        for index, recording in enumerate(recordings[:MAX_RECORDINGS_EXPANDED]):
            if index:
                time.sleep(MUSICBRAINZ_RATE_LIMIT)
            releases = musicbrainz_releases(recording["id"], http)
            candidates.extend(
                candidates_from_musicbrainz(recording, releases, 0.0, source="youtube")
            )
        candidates.append(_synthetic_candidate(hint))
        itunes_term = " ".join(term for term in (hint.artist, hint.track) if term)

    if not itunes_term:
        itunes_term = guess_query_from_filename(path)

    try:
        response = http.get(ITUNES_ENDPOINT, params={
            "term": itunes_term, "entity": "song", "limit": 5,
        }, timeout=TIMEOUT)
        if getattr(response, "ok", False):
            candidates.extend(parse_itunes_response(response.json()))
    except Exception:
        pass

    return candidates
```

Note: `load_hint` returns `None` unless the hint is `usable`, so the `if
hint is not None:` branch already implies there is an artist, track, or
video_title to work with.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd y1sync && python -m pytest -v`
Expected: PASS — the whole `y1sync` suite. Pay attention to the
pre-existing `identify` tests that assert exact `session.calls`
(`test_falls_back_when_the_fingerprint_finds_nothing`,
`test_without_an_api_key_it_falls_back_to_the_filename`,
`test_falls_back_when_chromaprint_is_missing`,
`test_an_ordinary_http_failure_still_falls_back`): their fake paths have
no sidecar beside them, so `load_hint` returns `None` and the call
sequence is unchanged.

- [ ] **Step 5: Commit**

```bash
git add y1sync/src/y1sync/identify.py y1sync/tests/test_identify.py
git commit -m "feat: identify from the YouTube sidecar when the fingerprint is empty"
```

---

### Task 6: Review note and `--yes` message; guess-invariant test

**Files:**
- Modify: `y1sync/src/y1sync/review.py` (`choose_candidate`)
- Modify: `y1sync/src/y1sync/cli.py` (the `--yes` guess branch message,
  around line 375)
- Test: `y1sync/tests/test_review.py`, `y1sync/tests/test_cli.py`

**Interfaces:**
- Consumes: `Candidate.source == "youtube"` from Task 5.
- Produces: no new symbols. `choose_candidate` prints one extra
  informational line when the top-ranked candidate is `source="youtube"`;
  `cmd_scan`'s `--yes` refusal message names the YouTube page rather than
  the filename for such a pick.

- [ ] **Step 1: Write the failing tests**

Add to `y1sync/tests/test_review.py` (it imports `TrackMeta, Candidate`
and `choose_candidate`):

```python
def test_a_youtube_sourced_top_option_is_labelled_from_the_youtube_page():
    lines = []
    cand = Candidate(
        meta=TrackMeta(artist="SZA", title="Snooze", album="SOS", year="2022"),
        confidence=0.0, source="youtube", release_group_type="Album",
        release_status="Official", release_date=None,
    )
    choose_candidate(Path("snooze.mp3"), [cand],
                     input_fn=lambda _: "", output_fn=lines.append)
    assert any(
        "From the YouTube page: SZA — Snooze (SOS, 2022)" in line
        for line in lines
    )


def test_no_youtube_line_for_a_fingerprint_match():
    lines = []
    choose_candidate(Path("f.mp3"), [cand("Rumours")],
                     input_fn=lambda _: "", output_fn=lines.append)
    assert not any("From the YouTube page" in line for line in lines)
```

Add to `y1sync/tests/test_cli.py` (near the other `--yes` tests, which
already define `_guess_candidate`):

```python
def _youtube_guess():
    return Candidate(
        meta=TrackMeta(artist="Some DIY Act", title="Basement Tape", album="EP"),
        confidence=0.0, source="youtube", release_group_type="Album",
        release_status="Official", release_date=None,
    )


def test_yes_refuses_a_youtube_sourced_pick(tmp_path, capsys, monkeypatch):
    (tmp_path / "basement tape.mp3").write_bytes(b"one")
    monkeypatch.setattr("y1sync.cli.identify",
                        lambda p, api_key=None, session=None: [_youtube_guess()])
    monkeypatch.setattr("y1sync.cli.CACHE_ROOT", tmp_path / "cache")

    main(["scan", str(tmp_path), "--dry-run", "--yes"])
    out = capsys.readouterr().out.lower()

    assert "needs review" in out
    assert "youtube page" in out
    assert "would tag and rename" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd y1sync && python -m pytest tests/test_review.py tests/test_cli.py -k "youtube" -v`
Expected: FAIL — no "From the YouTube page" line is printed; the `--yes`
message still says "identified from its filename".

- [ ] **Step 3: Write the implementation**

**(a)** In `y1sync/src/y1sync/review.py`, `choose_candidate`: it computes
`ranked = rank_candidates(candidates)` near the top and then prints

```python
    output_fn(f"\n{header}")
    output_fn(f"  {Path(path).name}")
```

Immediately after that second `output_fn`, add:

```python
    if ranked and ranked[0].source == "youtube":
        top = ranked[0]
        detail = ", ".join(part for part in (top.meta.album, top.meta.year) if part)
        suffix = f" ({detail})" if detail else ""
        output_fn(
            f"  From the YouTube page: {top.meta.artist} — {top.meta.title}{suffix}"
        )
```

(`—` is the em dash the module already uses in `_group_header`; a
literal `—` is fine too — match whatever the file does.)

**(b)** In `y1sync/src/y1sync/cli.py`, `cmd_scan`, the first `--yes`
refusal branch currently reads:

```python
                if needs_review and yes and _is_a_guess(pick):
                    ...
                    unconfirmed.append(f"{path.name} -> {pick.meta.artist} - {pick.meta.title}")
                    print(f"  needs review  {path.name} (identified from its filename)")
                    continue
```

Change the `print` to name the source:

```python
                    why = (
                        "identified from the YouTube page, not its audio"
                        if pick.source == "youtube"
                        else "identified from its filename"
                    )
                    print(f"  needs review  {path.name} ({why})")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd y1sync && python -m pytest -v`
Expected: PASS — full `y1sync` suite, including the pre-existing
`test_yes_refuses_to_accept_a_filename_guess` (an `itunes` pick still
prints "identified from its filename").

- [ ] **Step 5: Commit**

```bash
git add y1sync/src/y1sync/review.py y1sync/src/y1sync/cli.py \
        y1sync/tests/test_review.py y1sync/tests/test_cli.py
git commit -m "feat: label a YouTube-sourced match as coming from the page, not the audio"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Modify: `README.md`, `y1sync/README.md`, `yt2mp3/README.md`

**Interfaces:** none — prose only.

- [ ] **Step 1: CHANGELOG entry**

Under `## [Unreleased]`, add to the existing `### Added` list (keep the
house style — bold lead sentence, then the why, concrete where possible):

```markdown
- **A track the fingerprint can't place is now identified from what
  YouTube said it was, not just its filename.** `yt2mp3` writes a small
  `<name>.yt2mp3.json` beside each download holding the artist, title,
  album and year yt-dlp pulled from the video (a YouTube Music "- Topic"
  channel, or the "Provided to YouTube by" block in the description).
  When AcoustID returns no match — common for lesser-known and
  independent tracks — `y1sync` uses that to text-search MusicBrainz for
  the real release and to seed the iTunes lookup, instead of guessing
  from a noisy filename. The result still goes to review and `--yes`
  still refuses it: nothing but a fingerprint is applied unseen. No
  sidecar (a hand-managed library, or a file downloaded another way)
  means the old filename behaviour, unchanged.
```

- [ ] **Step 2: README mentions**

In the top-level `README.md`, the two-tool summary near the top currently
reads:

```markdown
- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3.
```

Extend it:

```markdown
- **[yt2mp3](yt2mp3/)** — download a YouTube video or playlist as MP3,
  and drop a small `.yt2mp3.json` sidecar of what YouTube said the track
  was next to each file.
```

In `yt2mp3/README.md`, add a short paragraph (place it after the usage
section, matching existing heading style):

```markdown
## The metadata sidecar

Next to every MP3 it writes, `yt2mp3` leaves a `<name>.yt2mp3.json` file
with the artist, title, album and year yt-dlp extracted from the video.
It costs nothing if you don't use it, and it's what lets `y1sync`
identify a track that audio fingerprinting can't place without falling
back to guessing from the filename. Delete them freely; they're
regenerated on the next download.
```

In `y1sync/README.md`, find the section explaining identification (the
"How does it identify tracks?" material or the fingerprint discussion)
and add a sentence:

```markdown
When fingerprinting draws a blank — which happens most for obscure and
independent tracks — `y1sync` looks for a `.yt2mp3.json` sidecar left by
`yt2mp3` and identifies from that (a MusicBrainz search for the real
release, seeded with YouTube's own artist and title) rather than from the
filename. It's still shown for review; only a fingerprint match is ever
applied automatically.
```

- [ ] **Step 3: Verify the docs build/read cleanly**

Run: `cd y1sync && python -m pytest && cd ../yt2mp3 && python -m pytest`
Expected: PASS (no test change; this is the final green-suite check).
Re-read each edited Markdown file to confirm list nesting and heading
levels match the surrounding document.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md y1sync/README.md yt2mp3/README.md
git commit -m "docs: describe the yt2mp3 metadata sidecar and its use in y1sync"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| `yt2mp3/src/yt2mp3/metadata.py` — `write_sidecar`, field extraction, list-join, year fallback, schema envelope, best-effort | Task 1 |
| `downloader.py` — call `write_sidecar` in the mp3 postprocessor hook; covers standalone CLI and menu flow | Task 2 |
| `y1sync/src/y1sync/hint.py` — `YtHint`, `load_hint`, defensive parse, "nothing usable → None" | Task 3 |
| `identify.py` — `source` param on `candidates_from_musicbrainz` | Task 4 |
| `identify.py` — `musicbrainz_recording_search` (Lucene query, normalised shape, `[]` on failure) | Task 4 |
| `identify.py` — hint-aware fallback: MB search + synthesized candidate + hint-seeded iTunes; filename path when no hint | Task 5 |
| Invariant: hint candidates `source="youtube"`, `confidence=0.0`, routed to review, refused by `--yes` | Task 5 (sources), Task 6 (`--yes` test) |
| `review.py` — "From the YouTube page:" line | Task 6 |
| Ranking: synthesized candidate has `release_date=None` so real releases outrank it; no `ranking.py` change | Task 5 (`_synthetic_candidate`); verified by `test_a_synthesized_candidate_survives…` and existing ranking tests |
| Caching: hint candidates cached like any other, no change | No code change; `Candidate` is unchanged, `cache._to_json/_from_json` already round-trip every field |
| Device sync untouched; sidecars never copied | No code change; `_find_mp3s` globs `*.mp3` only — stated in spec, nothing to implement |
| CHANGELOG + READMEs | Task 7 |

No gaps.

**2. Placeholder scan**

No "TBD"/"handle edge cases"/"similar to Task N"/"write tests for the
above" — every code and test step carries literal content. Error paths
are concrete (`except OSError` in `write_sidecar`, `(OSError,
json.JSONDecodeError)` in `load_hint`, `except Exception: return []` in
`musicbrainz_recording_search`, `except Exception: pass` around the
iTunes call).

**3. Type consistency**

- `write_sidecar(info: dict, mp3_path: str | Path) -> None` — same name
  and signature in Task 1 (produced) and Task 2 (consumed).
- `sidecar_path` (Task 1) vs `hint._sidecar_for` (Task 3): deliberately
  separate — the two packages do not import each other. Both build
  `stem + ".yt2mp3.json"`; both pin the suffix to a module constant
  `SIDECAR_SUFFIX` with the same value. A cross-package test is not
  possible without a dependency; the shared literal is asserted in each
  package's own tests (`test_sidecar_path_sits_next_to_the_mp3`,
  `_write` helper in `test_hint.py`).
- `YtHint` fields `artist, track, album, year, video_title, url` — used
  identically in Task 3 (definition), Task 5 (`_synthetic_candidate`,
  `_fallback`), Task 6 (test data). `.usable` referenced only inside
  `load_hint`.
- `candidates_from_musicbrainz(recording, releases, score, source=
  "acoustid")` — new 4th param defined in Task 4, called with
  `source="youtube"` in Task 5, default relied on by the untouched
  `_expand_acoustid` call site.
- `musicbrainz_recording_search(artist, track, album=None, session=None)
  -> list[dict]` with items `{"id", "title", "artists":[{"name"}],
  "duration"}` — the exact shape `musicbrainz_releases` +
  `candidates_from_musicbrainz` already consume from AcoustID hits.
- `_fallback(path, http) -> list[Candidate]` and `_synthetic_candidate(
  hint) -> Candidate` — defined and used only within `identify.py` (Task
  5).
- `Candidate` construction in `_synthetic_candidate` uses only existing
  fields (`meta, confidence, source, release_group_type, release_status,
  release_date`); `secondary_types` defaults to `()`, `stated_duration`
  and `artwork_url` to `None` — matches `models.Candidate`.

Consistent.

## Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-08-28-youtube-metadata-hint.md`. Two
execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review
between tasks, fast iteration.

**2. Inline Execution** — tasks run in this session via
`superpowers:executing-plans`, batched with checkpoints for review.

Which approach?
