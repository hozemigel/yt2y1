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


def _make_postprocessor_hook(downloaded_files: list[str] | None):
    """Build the postprocessor_hooks callback, optionally recording each
    finished MP3's path into downloaded_files.

    A caller that needs to know exactly what this download produced (y1sync
    does, to tag only the file it just fetched) can't get that from download()'s
    return value -- that's just yt-dlp's exit code -- or by comparing a
    folder listing before and after: if a file with the same name already
    exists (a track downloaded once before, or retried after an earlier
    attempt failed partway through), a before/after diff sees no new path
    and misses it entirely. yt-dlp already knows the exact path for certain,
    so it's taken from here instead.
    """
    def hook(d):
        if d.get("status") == "finished":
            info = d.get("info_dict", {})
            # postprocessor_hooks fires once per postprocessor in yt-dlp's
            # chain (e.g. FFmpegExtractAudio, then an internal file-move
            # step), each with a snapshot of info_dict taken before that
            # stage ran. Only the stages that run after conversion see the
            # final .mp3 path, so filter on the actual extension rather
            # than printing every "finished" event.
            if info.get("ext") != "mp3":
                return
            path = info.get("filepath") or info.get("_filename", "")
            print(f"Saved: {path}")
            if downloaded_files is not None:
                downloaded_files.append(path)
    return hook


def build_ydl_opts(opts: DownloadOptions, downloaded_files: list[str] | None = None) -> dict:
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
        "postprocessor_hooks": [_make_postprocessor_hook(downloaded_files)],
        "ignoreerrors": True,
        "noplaylist": not opts.playlist,
        # yt-dlp's defaults -- a 20s socket timeout, 10 retries -- are
        # tuned for a typical connection. Seen for real on a slower one:
        # repeated "Read timed out (read timeout=20.0)" fetching YouTube's
        # own player API, then the audio download itself cutting off
        # partway through and giving up. Both are raised so a slow or
        # flaky connection gets more time per request and more attempts
        # before the download is given up on.
        "socket_timeout": 30,
        "retries": 20,
        "fragment_retries": 20,
    }


def download(opts: DownloadOptions, downloaded_files: list[str] | None = None) -> int:
    """Run the download. If downloaded_files is given, each finished MP3's
    path is appended to it as the download progresses."""
    ydl_opts = build_ydl_opts(opts, downloaded_files)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.download([opts.url])
