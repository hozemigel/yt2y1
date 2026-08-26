from y1sync.models import TrackMeta, Candidate
from y1sync.cache import ContentCache


def make_candidate():
    return Candidate(
        meta=TrackMeta(artist="A", title="B", album="C", year="1999"),
        confidence=0.95, source="acoustid", release_group_type="Album",
        secondary_types=("Compilation",), release_status="Official",
        release_date="1999-01-01", artwork_url="https://example.test/a.jpg",
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
    assert restored == [make_candidate()]


def test_key_follows_content_not_filename(tmp_path):
    # Renaming a file must not discard its cached identification.
    cache = ContentCache(tmp_path / "cache")
    first = tmp_path / "before.mp3"
    first.write_bytes(b"same audio")
    cache.put(first, [make_candidate()])
    second = tmp_path / "after.mp3"
    second.write_bytes(b"same audio")
    assert cache.get(second) == [make_candidate()]


def test_different_content_misses(tmp_path):
    cache = ContentCache(tmp_path / "cache")
    first = tmp_path / "a.mp3"
    first.write_bytes(b"one")
    cache.put(first, [make_candidate()])
    second = tmp_path / "b.mp3"
    second.write_bytes(b"two")
    assert cache.get(second) is None
