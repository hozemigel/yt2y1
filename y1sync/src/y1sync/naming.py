"""Filename construction that survives FAT32, NTFS and Windows alike."""

import os
import re
import unicodedata
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

# Typographic punctuation mapped to ASCII equivalents so cheap FAT32-based
# players (Innioasis Y1) can display filenames correctly. Mirrors
# ranking._PUNCTUATION_VARIANTS but applied to what is written to disk.
TYPOGRAPHIC_VARIANTS = str.maketrans({
    # Dash family
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\u2012": "-",  # FIGURE DASH
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u2015": "-",  # HORIZONTAL BAR
    "\u2212": "-",  # MINUS SIGN
    # Single-quote family
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u201a": "'",  # SINGLE LOW-9 QUOTATION MARK
    "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2032": "'",  # PRIME
    # Double-quote family
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "\u201f": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2033": '"',  # DOUBLE PRIME
    # Ellipsis
    "\u2026": "...",  # HORIZONTAL ELLIPSIS
})


def sanitize_component(text: str) -> str:
    """Make one piece of a filename safe, preserving readability."""
    # 1. NFKD-normalise and drop combining marks so accented Latin letters
    #    reduce to their ASCII base (AVICI, Beyonce). Scripts with no ASCII
    #    decomposition (Cyrillic, CJK, etc.) are left intact.
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )
    # 2. Slash lookalikes (existing).
    for bad, good in SLASH_LOOKALIKES.items():
        text = text.replace(bad, good)
    # 3. Typographic punctuation -> ASCII equivalents.
    text = text.translate(TYPOGRAPHIC_VARIANTS)
    # 4. Filesystem-illegal characters, whitespace collapse, trim (existing).
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

    Raises FileExistsError rather than renaming onto another file.
    Path.rename overwrites atomically and silently, so without this guard
    a second rip of a track already in the folder would destroy the copy
    that was there — with no backup and no message.
    """
    target = path.with_name(new_name)
    if path.name == new_name:
        return path
    if path.name.lower() == new_name.lower():
        temp = path.with_name(f".y1sync-tmp-{path.name}")
        path.rename(temp)
        temp.rename(target)
        return target
    # lexists, not exists: a broken symlink occupies the name too.
    if os.path.lexists(target):
        raise FileExistsError(f"{target.name} already exists; refusing to overwrite it")
    path.rename(target)
    return target
