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
