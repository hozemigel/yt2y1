import argparse
import sys

from yt2mp3.checks import ensure_ffmpeg, FfmpegNotFoundError
from yt2mp3.downloader import DownloadOptions, download


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt2mp3",
        description="Download a YouTube video or playlist and convert it to MP3.",
    )
    parser.add_argument("url", help="Video or playlist URL")
    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "-q", "--quality",
        default="192",
        help="MP3 bitrate in kbps (default: 192)",
    )
    parser.add_argument(
        "--filename-template",
        default="%(title)s.%(ext)s",
        help="yt-dlp output filename template (default: %%(title)s.%%(ext)s)",
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
    )
    return download(opts)


if __name__ == "__main__":
    sys.exit(main())
