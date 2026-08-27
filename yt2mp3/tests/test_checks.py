import pytest
from yt2mp3.checks import ensure_ffmpeg, FfmpegNotFoundError


def test_ensure_ffmpeg_raises_when_missing():
    with pytest.raises(FfmpegNotFoundError):
        ensure_ffmpeg(which_fn=lambda name: None)


def test_ensure_ffmpeg_passes_when_present():
    ensure_ffmpeg(which_fn=lambda name: "/usr/bin/ffmpeg")


def test_ensure_ffmpeg_error_message_mentions_install():
    with pytest.raises(FfmpegNotFoundError, match="ffmpeg"):
        ensure_ffmpeg(which_fn=lambda name: None)
