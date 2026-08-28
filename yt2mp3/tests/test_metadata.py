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
