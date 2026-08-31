from pathlib import Path

from y1sync.formats import (
    SUPPORTED_EXTENSIONS, device_target_name, find_audio, is_supported,
)


def test_supported_extensions_cover_the_common_lossy_and_lossless_set():
    assert SUPPORTED_EXTENSIONS == {".mp3", ".flac", ".ogg", ".m4a", ".wav"}


def test_is_supported_is_case_insensitive(tmp_path):
    assert is_supported(tmp_path / "a.FLAC")
    assert not is_supported(tmp_path / "a.ape")


def test_find_audio_picks_up_every_supported_format(tmp_path):
    for name in ("a.mp3", "b.flac", "c.ogg", "d.m4a", "e.wav"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "skip.ape").write_bytes(b"x")
    (tmp_path / "cover.jpg").write_bytes(b"x")

    found = [p.name for p in find_audio(tmp_path)]

    assert found == ["a.mp3", "b.flac", "c.ogg", "d.m4a", "e.wav"]


def test_find_audio_recurses_into_album_folders(tmp_path):
    album = tmp_path / "Artist" / "Album"
    album.mkdir(parents=True)
    (album / "01 track.flac").write_bytes(b"x")

    assert find_audio(tmp_path) == [album / "01 track.flac"]


def test_device_target_name_turns_wav_into_flac():
    assert device_target_name(Path("Artist/Song.wav")) == Path("Artist/Song.flac")
    assert device_target_name(Path("Song.WAV")) == Path("Song.flac")


def test_device_target_name_leaves_other_formats_alone():
    for name in ("Song.mp3", "Song.flac", "Song.ogg", "Song.m4a"):
        assert device_target_name(Path(name)) == Path(name)
