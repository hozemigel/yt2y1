"""Which audio formats y1sync scans, tags and renames.

The Innioasis Y1 plays a long list of formats. This is the subset
`mutagen` can also *write tags into* — the ones y1sync can identify and
label rather than merely copy. Everything else (APE, AMR, MIDI, AC3,
raw AAC streams, ...) is left where it is.
"""

from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".flac", ".ogg", ".m4a", ".wav"})


def is_supported(path: Path) -> bool:
    """True when path's extension is one y1sync can tag."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_audio(root: Path) -> list[Path]:
    """Every supported audio file under root, at any depth, sorted.

    A library organised into artist/album folders is the normal case, not
    an edge case: iterdir() alone would miss almost everything a real
    music collection contains.
    """
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def device_target_name(path: Path) -> Path:
    """The name a source file takes once it is on the device.

    WAV becomes FLAC: the Y1 plays WAV but reads nothing from its tags —
    no artist, no album, no cover — so a WAV goes to the device as a
    lossless FLAC instead, which it does tag correctly. Every other format
    keeps its name. Pass a path relative to the library root so the
    device tree still mirrors it.
    """
    path = Path(path)
    if path.suffix.lower() == ".wav":
        return path.with_suffix(".flac")
    return path
