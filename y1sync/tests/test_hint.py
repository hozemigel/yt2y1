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
