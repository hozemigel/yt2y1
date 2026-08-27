import argparse
import os
import sys

from yt2mp3.checks import ensure_ffmpeg, FfmpegNotFoundError
from yt2mp3.downloader import DownloadOptions, download

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/yt2mp3/pesme")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt2mp3",
        description="Download a YouTube video or playlist and convert it to MP3.",
    )
    parser.add_argument("url", help="Video or playlist URL")
    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-q", "--quality",
        default="320",
        help="MP3 bitrate in kbps (default: 320)",
    )
    parser.add_argument(
        "--filename-template",
        default="%(title)s.%(ext)s",
        help="yt-dlp output filename template (default: %%(title)s.%%(ext)s)",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        # A single video's URL carries the same list= parameter as an
        # intentional playlist whenever it was opened from one -- including
        # YouTube's auto-generated "Mix" radio links, which can run to
        # hundreds of tracks. Downloading just that one video is the far
        # more common intent, so it's the default; this opts into the rest.
        help="Download the whole playlist the URL belongs to, "
             "not just the one video (default: single video only)",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        ensure_ffmpeg()
    except FfmpegNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    opts = DownloadOptions(
        url=args.url,
        output_dir=args.output_dir,
        quality=args.quality,
        filename_template=args.filename_template,
        playlist=args.playlist,
    )
    return download(opts)


if __name__ == "__main__":
    sys.exit(main())
