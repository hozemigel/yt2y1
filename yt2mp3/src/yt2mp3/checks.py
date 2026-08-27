import shutil


class FfmpegNotFoundError(RuntimeError):
    pass


def ensure_ffmpeg(which_fn=shutil.which) -> None:
    if which_fn("ffmpeg") is None:
        raise FfmpegNotFoundError(
            "ffmpeg not found on PATH. Install it:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
