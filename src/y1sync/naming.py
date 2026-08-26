"""Filename construction that survives FAT32, NTFS and Windows alike."""

import re
from pathlib import Path

from .models import TrackMeta

# Unicode characters that look like a slash. YouTube rips contain these
# because the real "/" is illegal in a filename.
SLASH_LOOKALIKES = {
    "⧸": "-",  # BIG SOLIDUS
    "⁄": "-",  # FRACTION SLASH
    "∕": "-",  # DIVISION SLASH
    "／": "-",  # FULLWIDTH SOLIDUS
}

ILLEGAL_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

WINDOWS_RESERVED = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def sanitize_component(text: str) -> str:
    """Make one piece of a filename safe, preserving readability."""
    for bad, good in SLASH_LOOKALIKES.items():
        text = text.replace(bad, good)
    text = ILLEGAL_PATTERN.sub("-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def safe_filename(meta: TrackMeta, max_len: int = 100) -> str:
    """Build "Artist - Title.mp3", safe on every supported platform."""
    artist = sanitize_component(meta.artist)
    title = sanitize_component(meta.title)
    stem = f"{artist} - {title}".strip(" -") if artist else title
    stem = stem[:max_len].strip(" .")
    if not stem:
        stem = "Unknown"
    # A file named CON.mp3 cannot be opened on Windows.
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"{stem}_"
    return f"{stem}.mp3"


def resolve_collision(name: str, taken: set[str]) -> str:
    """Append " (2)", " (3)" until the name is free.

    Comparison is case-insensitive because FAT32 is.
    """
    lowered = {t.lower() for t in taken}
    if name.lower() not in lowered:
        return name
    stem, _, ext = name.rpartition(".")
    counter = 2
    while f"{stem} ({counter}).{ext}".lower() in lowered:
        counter += 1
    return f"{stem} ({counter}).{ext}"


def rename_file(path: Path, new_name: str) -> Path:
    """Rename a file, correctly handling case-only changes.

    On a case-insensitive filesystem, renaming "Black" to "BLACK" is a
    no-op that silently does nothing. Routing through a temporary name
    forces the change to take effect.
    """
    target = path.with_name(new_name)
    if path.name == new_name:
        return path
    if path.name.lower() == new_name.lower():
        temp = path.with_name(f".y1sync-tmp-{path.name}")
        path.rename(temp)
        temp.rename(target)
        return target
    path.rename(target)
    return target
