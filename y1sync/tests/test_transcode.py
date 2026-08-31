import pytest

from mutagen.flac import FLAC

from y1sync.models import TrackMeta
from y1sync.tagging import write_tags
from y1sync.transcode import TranscodeError, wav_to_flac

META = TrackMeta(
    artist="Portishead", title="Roads", album="Dummy",
    year="1994", genre="Trip-Hop", track_number=10,
)


def test_produces_a_flac_of_the_wav_audio(make_audio, tmp_path):
    wav = make_audio(".wav")
    out = tmp_path / "out.flac"

    wav_to_flac(wav, out)

    flac = FLAC(out)
    assert flac.info.length == pytest.approx(8, abs=0.2)


def test_carries_tags_and_cover_across(make_audio, tmp_path):
    wav = make_audio(".wav")
    write_tags(wav, META, artwork=b"\xff\xd8\xff" + b"z" * 3000)
    out = tmp_path / "out.flac"

    wav_to_flac(wav, out)

    flac = FLAC(out)
    assert flac["title"] == ["Roads"]
    assert flac["artist"] == ["Portishead"]
    assert flac["albumartist"] == ["Portishead"]
    assert flac["date"] == ["1994"]
    assert flac["tracknumber"] == ["10"]
    assert len(flac.pictures) == 1


def test_output_is_16_bit_so_the_device_can_decode_it(tmp_path):
    import subprocess
    from mutagen.flac import FLAC

    hires = tmp_path / "hires.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2",
         "-c:a", "pcm_s24le", "-ar", "96000", str(hires)],
        check=True,
    )
    out = tmp_path / "out.flac"

    wav_to_flac(hires, out)

    info = FLAC(out).info
    assert info.bits_per_sample == 16
    assert info.sample_rate <= 48000


def test_cd_shaped_wav_keeps_its_sample_rate(tmp_path):
    import subprocess
    from mutagen.flac import FLAC

    cd = tmp_path / "cd.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2",
         "-c:a", "pcm_s16le", "-ar", "44100", str(cd)],
        check=True,
    )
    out = tmp_path / "out.flac"

    wav_to_flac(cd, out)

    assert FLAC(out).info.sample_rate == 44100


def test_untagged_wav_still_converts(make_audio, tmp_path):
    wav = make_audio(".wav")
    out = tmp_path / "out.flac"

    wav_to_flac(wav, out)

    assert FLAC(out).info.length > 0


def test_mirrors_source_mtime_onto_the_flac(make_audio, tmp_path):
    wav = make_audio(".wav")
    import os
    os.utime(wav, (1_600_000_000, 1_600_000_000))
    out = tmp_path / "out.flac"

    wav_to_flac(wav, out)

    assert out.stat().st_mtime == pytest.approx(1_600_000_000, abs=2)


def test_raises_transcode_error_on_a_bogus_wav(tmp_path):
    fake = tmp_path / "not-audio.wav"
    fake.write_bytes(b"this is not a RIFF file")
    with pytest.raises(TranscodeError):
        wav_to_flac(fake, tmp_path / "out.flac")

    assert not (tmp_path / "out.flac").exists()
