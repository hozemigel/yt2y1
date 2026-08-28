import json
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


def test_downloaded_files_collects_the_finished_mp3s_path(monkeypatch):
    # A caller that needs the exact path yt-dlp just wrote (y1sync does, to
    # tag only the file it just fetched) reads it from here -- not from a
    # folder listing, which can't tell a freshly written file from one that
    # already existed under the same name.
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            # Simulates yt-dlp's own postprocessor chain: a non-mp3 stage
            # fires first and must be ignored, then the real one.
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {"ext": "m4a"}})
                hook({"status": "finished",
                      "info_dict": {"ext": "mp3", "filepath": "/music/Song.mp3"}})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    downloaded_files: list[str] = []
    rc = download(DownloadOptions(url="https://youtu.be/x"), downloaded_files)

    assert rc == 0
    assert downloaded_files == ["/music/Song.mp3"]


def test_downloaded_files_defaults_to_not_collecting(monkeypatch):
    # download()'s existing callers (yt2mp3's own CLI) don't pass this and
    # must not be required to -- the hook has to tolerate None.
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished",
                      "info_dict": {"ext": "mp3", "filepath": "/music/Song.mp3"}})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    rc = download(DownloadOptions(url="https://youtu.be/x"))

    assert rc == 0


def test_download_writes_a_sidecar_next_to_the_mp3(monkeypatch, tmp_path):
    mp3 = tmp_path / "Song.mp3"

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {
                    "ext": "mp3", "filepath": str(mp3),
                    "title": "SZA - Snooze", "artist": "SZA", "track": "Snooze",
                    "album": "SOS", "release_year": "2022", "channel": "SZAVEVO",
                    "webpage_url": "https://youtu.be/x",
                }})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    from yt2mp3.metadata import sidecar_path
    download(DownloadOptions(url="https://youtu.be/x", output_dir=str(tmp_path)))

    body = json.loads(sidecar_path(mp3).read_text(encoding="utf-8"))
    assert body["artist"] == "SZA"
    assert body["track"] == "Snooze"
    assert body["year"] == "2022"


def test_a_sidecar_write_failure_does_not_break_the_download(monkeypatch):
    # filepath points into a directory that does not exist: write_sidecar
    # swallows the OSError, and the download still reports success and
    # still records the path for its caller.
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            for hook in self.opts["postprocessor_hooks"]:
                hook({"status": "finished", "info_dict": {
                    "ext": "mp3", "filepath": "/no/such/dir/Song.mp3",
                }})
            return 0

    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYDL)

    collected: list[str] = []
    rc = download(DownloadOptions(url="https://youtu.be/x"), collected)

    assert rc == 0
    assert collected == ["/no/such/dir/Song.mp3"]
