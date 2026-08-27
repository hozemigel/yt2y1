import os
from dataclasses import dataclass

import yt_dlp


@dataclass
class DownloadOptions:
    url: str
    output_dir: str = "."
    quality: str = "320"
    filename_template: str = "%(title)s.%(ext)s"
    # yt-dlp downloads the whole playlist by default whenever a URL carries
    # a list= parameter -- which includes YouTube's auto-generated "Mix"
    # radio links, not just playlists a user actually built. A single video
    # link opened from a Mix carries that parameter too, so the naive
    # default silently turns "get me this one song" into a few-hundred-track
    # download. Single-video is the safer default; playlist=True opts in.
    playlist: bool = False


def _progress_hook(d):
    if d.get("status") == "finished":
        title = d.get("info_dict", {}).get("title", d.get("filename", ""))
        print(f"Converting: {title}")
    elif d.get("status") == "downloading":
        title = d.get("info_dict", {}).get("title", d.get("filename", ""))
        print(f"Downloading: {title}", end="\r")


def _postprocessor_hook(d):
    if d.get("status") == "finished":
        info = d.get("info_dict", {})
        # postprocessor_hooks fires once per postprocessor in yt-dlp's chain
        # (e.g. FFmpegExtractAudio, then an internal file-move step), each with
        # a snapshot of info_dict taken before that stage ran. Only the stages
        # that run after conversion see the final .mp3 path, so filter on the
        # actual extension rather than printing every "finished" event.
        if info.get("ext") != "mp3":
            return
        path = info.get("filepath") or info.get("_filename", "")
        print(f"Saved: {path}")


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
        "postprocessor_hooks": [_postprocessor_hook],
        "ignoreerrors": True,
        "noplaylist": not opts.playlist,
    }


def download(opts: DownloadOptions) -> int:
    ydl_opts = build_ydl_opts(opts)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.download([opts.url])
