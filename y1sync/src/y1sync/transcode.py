"""Turn a WAV into a tagged FLAC for the device.

The Innioasis Y1 plays WAV but ignores its tags completely — no artist,
no album, no cover art. FLAC loses nothing coming from a WAV, is roughly
half the size, and the Y1 does read its Vorbis comments and picture
block. So `sync` puts a library WAV on the device as FLAC; the user's
own WAV is never touched.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError

from .device import safe_copy
from .tagging import read_artwork, read_tags, write_tags

# The Y1's FLAC decoder is the cheap-hardware kind: it plays CD-shaped
# FLAC and rejects anything hi-res with a "broken file" error. ffmpeg,
# left to itself, encodes a 24-bit FLAC from a float or 24-bit source, so
# the output is pinned to 16-bit and capped at 48 kHz. A CD-rip WAV is
# already 16-bit/44.1 and passes through untouched; a hi-res master loses
# only what the device could not have played anyway.
_MAX_BITS = 16
_MAX_RATE = 48000


class TranscodeError(RuntimeError):
    """ffmpeg could not turn the WAV into a FLAC."""


def _resample_args(src: Path) -> list[str]:
    """ffmpeg args to bring src within what the Y1 can decode."""
    args = ["-sample_fmt", "s16"]
    try:
        rate = MutagenFile(src).info.sample_rate
    except (MutagenError, OSError, ValueError, AttributeError):
        rate = None
    if rate and rate > _MAX_RATE:
        args += ["-ar", str(_MAX_RATE)]
    return args


def _read_meta(src: Path):
    """(meta, artwork) from src, or (None, None) if its tags won't parse.

    A WAV whose header is damaged should still be worth transcoding for
    its audio; ffmpeg below is the real judge of whether it is audio at
    all.
    """
    try:
        return read_tags(src), read_artwork(src)
    except (MutagenError, OSError, ValueError):
        return None, None


def wav_to_flac(src: Path, dst: Path) -> None:
    """Write dst as a FLAC of src's audio, carrying src's tags and cover.

    The encode lands in a local temp file first; only once it succeeds
    and the tags are on does it go to the device, through the same
    atomic, flushed write a plain copy uses. An interrupted run leaves
    nothing half-written on the device. dst's mtime is set to src's, so a
    later sync can tell an already-converted file from a changed one.
    """
    src, dst = Path(src), Path(dst)
    meta, artwork = _read_meta(src)

    with tempfile.TemporaryDirectory(prefix="y1sync-flac-") as work:
        local = Path(work) / "out.flac"
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(src), "-vn", "-map_metadata", "-1",
             "-c:a", "flac", *_resample_args(src), str(local)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not local.exists():
            raise TranscodeError(proc.stderr.strip() or "ffmpeg failed")
        if meta is not None:
            write_tags(local, meta, artwork)
        safe_copy(local, dst)

    stat = src.stat()
    os.utime(dst, (stat.st_atime, stat.st_mtime))
