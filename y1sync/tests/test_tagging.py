import pytest

from mutagen.id3 import ID3
from y1sync.models import TrackMeta
from y1sync.tagging import read_artwork, write_tags, read_tags

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


def test_write_tags_rejects_an_unsupported_extension(tmp_path):
    junk = tmp_path / "track.ape"
    junk.write_bytes(b"x")
    with pytest.raises(ValueError):
        write_tags(junk, META)


# --- non-MP3 formats ----------------------------------------------------

OTHER_FORMATS = [".flac", ".ogg", ".m4a", ".wav"]


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_round_trips_every_supported_format(make_audio, ext):
    path = make_audio(ext)
    write_tags(path, META)
    assert read_tags(path) == META


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_reads_none_before_anything_is_written(make_audio, ext):
    assert read_tags(make_audio(ext)) is None


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_omits_optional_fields_when_absent(make_audio, ext):
    path = make_audio(ext)
    write_tags(path, TrackMeta(artist="A", title="B", album="C"))
    restored = read_tags(path)
    assert (restored.year, restored.genre, restored.track_number) == (None, None, None)


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_embeds_a_single_cover(make_audio, ext):
    path = make_audio(ext)
    write_tags(path, META, artwork=b"\xff\xd8\xff" + b"x" * 2000)
    write_tags(path, META, artwork=b"\xff\xd8\xff" + b"y" * 2000)
    assert _cover_count(path, ext) == 1


@pytest.mark.parametrize("ext", OTHER_FORMATS)
def test_writing_twice_does_not_duplicate_fields(make_audio, ext):
    path = make_audio(ext)
    write_tags(path, META)
    write_tags(path, META)
    assert read_tags(path) == META


def test_flac_and_ogg_carry_an_album_artist(make_audio):
    for ext in (".flac", ".ogg"):
        path = make_audio(ext)
        write_tags(path, META)
        from mutagen import File
        assert File(path)["albumartist"] == [META.artist]


@pytest.mark.parametrize("ext", [".mp3", ".flac", ".ogg", ".m4a", ".wav"])
def test_read_artwork_round_trips(make_audio, ext):
    art = b"\xff\xd8\xff" + b"k" * 1800
    path = make_audio(ext)
    assert read_artwork(path) is None
    write_tags(path, META, artwork=art)
    assert read_artwork(path) == art


def test_read_artwork_is_none_for_an_unreadable_file(tmp_path):
    junk = tmp_path / "x.flac"
    junk.write_bytes(b"not a flac")
    assert read_artwork(junk) is None


def _cover_count(path, ext):
    from mutagen import File
    audio = File(path)
    if ext == ".flac":
        return len(audio.pictures)
    if ext == ".ogg":
        return len(audio.get("metadata_block_picture") or [])
    if ext == ".m4a":
        return len(audio.get("covr") or [])
    return len(audio.tags.getall("APIC"))
