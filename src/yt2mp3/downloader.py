import os
from dataclasses import dataclass

import yt_dlp


@dataclass
class DownloadOptions:
    url: str
    output_dir: str = "."
    quality: str = "192"
    filename_template: str = "%(title)s.%(ext)s"


def _progress_hook(d):
    if d.get("status") == "finished":
        print(f"✓ Saved: {d.get('filename', '')}")
    elif d.get("status") == "downloading":
        title = d.get("info_dict", {}).get("title", d.get("filename", ""))
        print(f"Downloading: {title}", end="\r")


def build_ydl_opts(opts: DownloadOptions) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(opts.output_dir, opts.filename_template),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": opts.quality,
            }
        ],
        "progress_hooks": [_progress_hook],
        "ignoreerrors": True,
    }


def download(opts: DownloadOptions) -> int:
    ydl_opts = build_ydl_opts(opts)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.download([opts.url])
