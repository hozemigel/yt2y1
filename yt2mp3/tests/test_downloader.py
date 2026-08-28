import os
from yt2mp3.downloader import DownloadOptions, build_ydl_opts, download
import yt2mp3.downloader as downloader_module


def test_build_ydl_opts_defaults():
    opts = DownloadOptions(url="https://youtu.be/x")
    d = build_ydl_opts(opts)
    assert d["format"] == "bestaudio/best"
    assert d["outtmpl"] == os.path.join(".", "%(title)s.%(ext)s")
    assert d["ignoreerrors"] is True
    assert d["socket_timeout"] == 30
    assert d["retries"] == 20
    assert d["fragment_retries"] == 20
    pp = d["postprocessors"][0]
    assert pp["key"] == "FFmpegExtractAudio"
    assert pp["preferredcodec"] == "mp3"
    assert pp["preferredquality"] == "320"


def test_defaults_to_single_video_even_with_a_playlist_url():
    # Found for real: a video opened from a YouTube auto-generated "Mix"
    # carries the same list= parameter as an intentional playlist, and
    # yt-dlp's own default would download the whole mix -- hundreds of
    # tracks -- for someone who wanted the one song they clicked.
    opts = DownloadOptions(url="https://youtu.be/x?list=RDxyz&start_radio=1")
    assert build_ydl_opts(opts)["noplaylist"] is True


def test_playlist_true_downloads_the_whole_playlist():
    opts = DownloadOptions(url="https://youtu.be/x?list=PLxyz", playlist=True)
    assert build_ydl_opts(opts)["noplaylist"] is False


def test_build_ydl_opts_custom_values():
    opts = DownloadOptions(
        url="https://youtu.be/x",
        output_dir="out",
        quality="320",
        filename_template="%(id)s.%(ext)s",
    )
    d = build_ydl_opts(opts)
    assert d["outtmpl"] == os.path.join("out", "%(id)s.%(ext)s")
    assert d["postprocessors"][0]["preferredquality"] == "320"


def test_download_invokes_ydl_download_with_url(monkeypatch):
    calls = {}

    class FakeYDL:
        def __init__(self, opts):
            calls["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            calls["urls"] = urls
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    opts = DownloadOptions(url="https://youtu.be/x")
    rc = download(opts)

    assert rc == 0
    assert calls["urls"] == ["https://youtu.be/x"]
    assert calls["opts"]["format"] == "bestaudio/best"


def test_download_returns_nonzero_retcode_from_ydl(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            return 1

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    opts = DownloadOptions(url="https://youtu.be/bad")
    rc = download(opts)

    assert rc == 1
