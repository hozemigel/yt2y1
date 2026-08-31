import shutil
import subprocess
import pytest


@pytest.fixture
def silent_mp3(tmp_path):
    """A one-second silent MP3, generated on demand.

    Skips the test if ffmpeg is unavailable rather than failing, so the
    suite stays usable on machines without it.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required to generate the test MP3")
    path = tmp_path / "silent.mp3"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-q:a", "9", "-y", str(path)],
        check=True,
        capture_output=True,
    )
    return path


# ffmpeg output args per format. Ogg uses ffmpeg's own Vorbis encoder
# rather than libvorbis: Homebrew dropped libvorbis from its default
# ffmpeg formula, so `-c:a libvorbis` fails on macOS CI. The built-in
# encoder needs `-strict experimental` and only does two channels, hence
# `-ac 2` (the lavfi sine source is mono). At the 8 s default length its
# fingerprint is byte-for-byte identical to libvorbis's.
_CODECS = {
    ".mp3": ["-c:a", "libmp3lame"],
    ".wav": ["-c:a", "pcm_s16le"],
    ".flac": ["-c:a", "flac"],
    ".ogg": ["-c:a", "vorbis", "-strict", "experimental", "-ac", "2"],
    ".m4a": ["-c:a", "aac"],
}


@pytest.fixture
def make_audio(tmp_path):
    """Factory for a short tone in any format y1sync supports.

    A 440 Hz tone rather than silence: chromaprint refuses to fingerprint
    pure digital silence ("Empty fingerprint"), and the cache keys
    non-MP3 files on their fingerprint.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is required to generate test audio")

    def _make(ext: str, seconds: int = 8, freq: int = 440, name: str = "sample",
              src: str | None = None):
        # A default 440 Hz tone is fine for tag round-trips. For anything
        # that leans on the *fingerprint* being distinctive, pass an
        # explicit src -- chromaprint maps pure tones an octave apart onto
        # the same chroma features and cannot tell 440 Hz from 880 Hz.
        path = tmp_path / f"{name}{ext}"
        source = src or f"sine=frequency={freq}:duration={seconds}"
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", source,
             "-t", str(seconds), *_CODECS[ext], "-y", str(path)],
            check=True,
            capture_output=True,
        )
        return path

    return _make
