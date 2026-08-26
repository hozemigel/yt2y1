from mutagen.id3 import ID3
from y1sync.models import TrackMeta
from y1sync.tagging import write_tags, read_tags

META = TrackMeta(
    artist="Fleetwood Mac", title="Dreams", album="Rumours",
    year="1977", genre="Rock", track_number=2,
)


def test_writes_id3v23_not_v24(silent_mp3):
    write_tags(silent_mp3, META)
    assert ID3(silent_mp3).version[:2] == (2, 3)


def test_uses_utf16_encoding(silent_mp3):
    # ID3v2.3 permits only ISO-8859-1 and UTF-16. UTF-8 is out of spec.
    write_tags(silent_mp3, META)
    tags = ID3(silent_mp3)
    for frame in ("TIT2", "TPE1", "TALB"):
        assert tags[frame].encoding == 1


def test_uses_tyer_not_tdrc(silent_mp3):
    write_tags(silent_mp3, META)
    # ID3(path) defaults to v2_version=4, which silently upgrades old-style
    # frames (TYER -> TDRC) on load regardless of what's actually on disk.
    # Load as v2.3 explicitly so this checks the frame that was actually
    # persisted, not mutagen's default v2.4-normalized view of it.
    tags = ID3(silent_mp3, v2_version=3)
    assert "TYER" in tags
    assert "TDRC" not in tags
    assert str(tags["TYER"].text[0]) == "1977"


def test_sets_album_artist_for_device_grouping(silent_mp3):
    write_tags(silent_mp3, META)
    assert str(ID3(silent_mp3)["TPE2"].text[0]) == "Fleetwood Mac"


def test_embeds_artwork(silent_mp3):
    write_tags(silent_mp3, META, artwork=b"\xff\xd8\xff-fake-jpeg")
    apic = ID3(silent_mp3).getall("APIC")
    assert len(apic) == 1
    assert apic[0].type == 3
    assert apic[0].mime == "image/jpeg"


def test_writing_twice_does_not_duplicate_frames(silent_mp3):
    write_tags(silent_mp3, META, artwork=b"art")
    write_tags(silent_mp3, META, artwork=b"art")
    tags = ID3(silent_mp3)
    assert len(tags.getall("APIC")) == 1
    assert len(tags.getall("TIT2")) == 1


def test_omits_optional_frames_when_absent(silent_mp3):
    write_tags(silent_mp3, TrackMeta(artist="A", title="B", album="C"))
    tags = ID3(silent_mp3)
    assert "TYER" not in tags
    assert "TCON" not in tags
    assert "TRCK" not in tags


def test_round_trips_through_read_tags(silent_mp3):
    write_tags(silent_mp3, META)
    assert read_tags(silent_mp3) == META


def test_read_tags_returns_none_for_untagged_file(silent_mp3):
    assert read_tags(silent_mp3) is None
