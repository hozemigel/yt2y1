import json

import pytest

from y1sync.models import TrackMeta, Candidate
from y1sync.cache import ContentCache, content_hash
from y1sync.tagging import write_tags


def make_candidate():
    return Candidate(
        meta=TrackMeta(artist="A", title="B", album="C", year="1999"),
        confidence=0.95, source="acoustid", release_group_type="Album",
        secondary_types=("Compilation",), release_status="Official",
        release_date="1999-01-01", stated_duration=211.0,
        artwork_url="https://example.test/a.jpg",
    )


def test_returns_none_for_unseen_file(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    assert ContentCache(tmp_path / "cache").get(audio) is None


def test_round_trips_candidates(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    cache = ContentCache(tmp_path / "cache")
    cache.put(audio, [make_candidate()])
    restored = cache.get(audio)
    assert restored.candidates == [make_candidate()]


def test_key_follows_content_not_filename(tmp_path):
    # Renaming a file must not discard its cached identification.
    cache = ContentCache(tmp_path / "cache")
    first = tmp_path / "before.mp3"
    first.write_bytes(b"same audio")
    cache.put(first, [make_candidate()])
    second = tmp_path / "after.mp3"
    second.write_bytes(b"same audio")
    assert cache.get(second).candidates == [make_candidate()]


def test_different_content_misses(tmp_path):
    cache = ContentCache(tmp_path / "cache")
    first = tmp_path / "a.mp3"
    first.write_bytes(b"one")
    cache.put(first, [make_candidate()])
    second = tmp_path / "b.mp3"
    second.write_bytes(b"two")
    assert cache.get(second) is None


def test_hash_ignores_the_id3_tag_region(silent_mp3):
    # write_tags embeds ID3 frames into the very file the cache keys on.
    # Hashing the whole file would change the key on every successful
    # scan, so the cache would never hit twice.
    before = content_hash(silent_mp3)
    write_tags(
        silent_mp3,
        TrackMeta(artist="A", title="B", album="C", year="1999", genre="Pop"),
        artwork=b"\xff\xd8" + b"x" * 5000,
    )
    assert content_hash(silent_mp3) == before


def test_cache_hits_after_the_file_has_been_tagged(silent_mp3, tmp_path):
    cache = ContentCache(tmp_path / "cache")
    cache.put(silent_mp3, [make_candidate()])
    write_tags(silent_mp3, TrackMeta(artist="A", title="B", album="C"))
    entry = cache.get(silent_mp3)
    assert entry is not None
    assert entry.candidates == [make_candidate()]


def test_hash_still_distinguishes_different_audio(silent_mp3, tmp_path):
    other = tmp_path / "other.mp3"
    other.write_bytes(silent_mp3.read_bytes() + b"\x00" * 4096)
    assert content_hash(other) != content_hash(silent_mp3)


def test_remembers_the_chosen_candidate(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    cache = ContentCache(tmp_path / "cache")
    chosen = make_candidate()
    cache.put(audio, [chosen, make_candidate()], choice=chosen)
    entry = cache.get(audio)
    assert entry.choice == chosen


def test_choice_is_absent_until_one_is_made(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    cache = ContentCache(tmp_path / "cache")
    cache.put(audio, [make_candidate()])
    assert cache.get(audio).choice is None


def test_round_trips_the_recording_length(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    cache = ContentCache(tmp_path / "cache")
    cache.put(audio, [make_candidate()])
    assert cache.get(audio).candidates[0].stated_duration == 211.0


OTHER_FORMATS = [".flac", ".ogg", ".m4a", ".wav"]


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_hash_survives_tagging_for_every_format(make_audio, ext):
    # The whole point of the cache: a scan that tags a file must still
    # find that file's entry on the next run.
    path = make_audio(ext)
    before = content_hash(path)
    write_tags(
        path,
        TrackMeta(artist="A", title="B", album="C", year="1999", genre="Pop"),
        artwork=b"\xff\xd8\xff" + b"x" * 5000,
    )
    assert content_hash(path) == before


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_cache_hits_after_a_non_mp3_file_is_tagged(make_audio, ext, tmp_path):
    path = make_audio(ext)
    cache = ContentCache(tmp_path / "cache")
    cache.put(path, [make_candidate()])
    write_tags(path, TrackMeta(artist="A", title="B", album="C"))
    entry = cache.get(path)
    assert entry is not None
    assert entry.candidates == [make_candidate()]


def test_hash_distinguishes_different_non_mp3_audio(make_audio):
    tone = make_audio(".flac", name="a")
    noise = make_audio(".flac", name="b", src="anoisesrc=color=pink:seed=1")
    assert content_hash(tone) != content_hash(noise)


def test_loads_an_entry_written_before_stated_duration_existed(tmp_path):
    # Old cache files simply omit the key; they must still load.
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    cache = ContentCache(tmp_path / "cache")
    legacy = {
        "candidates": [{
            "meta": {"artist": "A", "title": "B", "album": "C", "year": "1999",
                     "genre": None, "track_number": None},
            "confidence": 0.9, "source": "acoustid", "release_group_type": "Album",
            "secondary_types": [], "release_status": "Official",
            "release_date": "1999-01-01", "artwork_url": None,
        }],
        "choice": None,
    }
    cache._path_for(audio).write_text(json.dumps(legacy), encoding="utf-8")
    assert cache.get(audio).candidates[0].stated_duration is None
