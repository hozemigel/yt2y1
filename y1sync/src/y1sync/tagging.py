"""ID3v2.3 tag writing, targeting what the Innioasis Y1 actually reads."""

from pathlib import Path

from mutagen.id3 import (
    ID3, ID3NoHeaderError, APIC, TALB, TCON, TIT2, TPE1, TPE2, TRCK, TYER,
)

from .models import TrackMeta

# ID3v2.3 allows only ISO-8859-1 (0) and UTF-16 (1). UTF-8 (3) is a v2.4
# addition; mutagen silently downgrades it, and relying on that would be
# depending on a library's incidental behaviour.
UTF16 = 1


def write_tags(path: Path, meta: TrackMeta, artwork: bytes | None = None) -> None:
    """Write meta to path as ID3v2.3, replacing any existing tags."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    # Clearing first keeps repeated runs idempotent: without it, mutagen
    # would accumulate duplicate APIC frames.
    tags.delete()

    tags.add(TIT2(encoding=UTF16, text=meta.title))
    tags.add(TPE1(encoding=UTF16, text=meta.artist))
    tags.add(TPE2(encoding=UTF16, text=meta.artist))
    tags.add(TALB(encoding=UTF16, text=meta.album))
    if meta.year:
        tags.add(TYER(encoding=UTF16, text=meta.year))
    if meta.genre:
        tags.add(TCON(encoding=UTF16, text=meta.genre))
    if meta.track_number is not None:
        tags.add(TRCK(encoding=UTF16, text=str(meta.track_number)))
    if artwork:
        tags.add(APIC(encoding=UTF16, mime="image/jpeg", type=3,
                      desc="Cover", data=artwork))

    tags.save(path, v2_version=3)


def read_tags(path: Path) -> TrackMeta | None:
    """Read tags back, or None if the file has none."""
    try:
        # mutagen's ID3() defaults to v2_version=4, which silently upgrades
        # old-style frames (TYER -> TDRC) on load regardless of what's
        # actually on disk. This file is v2.3, so read it back as v2.3 or
        # the TYER frame this module writes would never be seen.
        tags = ID3(path, v2_version=3)
    except ID3NoHeaderError:
        return None
    if "TIT2" not in tags:
        return None

    def text(frame: str) -> str | None:
        return str(tags[frame].text[0]) if frame in tags else None

    track = text("TRCK")
    return TrackMeta(
        artist=text("TPE1") or "",
        title=text("TIT2") or "",
        album=text("TALB") or "",
        year=text("TYER"),
        genre=text("TCON"),
        track_number=int(track) if track and track.isdigit() else None,
    )
