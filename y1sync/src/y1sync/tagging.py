"""Tag writing, targeting what the Innioasis Y1 actually reads.

The Y1 plays far more than MP3, so y1sync tags each format in the scheme
that format's readers expect:

* **MP3, WAV** -- ID3v2.3. UTF-16 text, ``TYER`` rather than ``TDRC``:
  v2.3 is the dialect cheap firmware understands, and mutagen's v2.4
  default silently rewrites both.
* **FLAC, Ogg** -- Vorbis comments, with an ``ALBUMARTIST`` mirror of the
  artist so the device groups an album under one name.
* **M4A** -- the iTunes-style MP4 atoms.

Every path is idempotent: writing twice leaves exactly one of each field
and a single cover.
"""

import base64
from pathlib import Path

from mutagen import MutagenError
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    ID3, ID3NoHeaderError, APIC, TALB, TCON, TIT2, TPE1, TPE2, TRCK, TYER,
)
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from .models import TrackMeta

# ID3v2.3 allows only ISO-8859-1 (0) and UTF-16 (1). UTF-8 (3) is a v2.4
# addition; mutagen silently downgrades it, and relying on that would be
# depending on a library's incidental behaviour.
UTF16 = 1

_ID3 = {".mp3", ".wav"}
_VORBIS = {".flac", ".ogg"}


def write_tags(path: Path, meta: TrackMeta, artwork: bytes | None = None) -> None:
    """Write meta to path, replacing any existing tags.

    Raises ValueError for an extension y1sync does not tag -- callers are
    expected to have filtered with formats.SUPPORTED_EXTENSIONS first.
    """
    ext = Path(path).suffix.lower()
    if ext in _ID3:
        _write_id3(path, ext, meta, artwork)
    elif ext in _VORBIS:
        _write_vorbis(path, ext, meta, artwork)
    elif ext == ".m4a":
        _write_mp4(path, meta, artwork)
    else:
        raise ValueError(f"can't tag {ext or 'a file with no extension'}")


def read_tags(path: Path) -> TrackMeta | None:
    """Read tags back, or None if the file carries none."""
    ext = Path(path).suffix.lower()
    if ext in _ID3:
        return _read_id3(path, ext)
    if ext in _VORBIS:
        return _read_vorbis(path)
    if ext == ".m4a":
        return _read_mp4(path)
    raise ValueError(f"can't read tags from {ext or 'a file with no extension'}")


def read_artwork(path: Path) -> bytes | None:
    """The embedded cover image bytes, or None when the file has none.

    Missing or unreadable artwork is not an error here, mirroring
    fetch_artwork(): a track with correct tags and no cover is fine.
    """
    ext = Path(path).suffix.lower()
    try:
        if ext in _ID3:
            tags = WAVE(path).tags if ext == ".wav" else ID3(path)
            frames = tags.getall("APIC") if tags else []
            return frames[0].data if frames else None
        if ext == ".flac":
            pictures = FLAC(path).pictures
            return pictures[0].data if pictures else None
        if ext == ".ogg":
            raw = OggVorbis(path).get("metadata_block_picture")
            return Picture(base64.b64decode(raw[0])).data if raw else None
        if ext == ".m4a":
            covers = MP4(path).get("covr")
            return bytes(covers[0]) if covers else None
    except (MutagenError, OSError, ValueError):
        return None
    return None


# --- ID3 (MP3, WAV) ---------------------------------------------------------

def _apply_id3(tags: ID3, meta: TrackMeta, artwork: bytes | None) -> None:
    # Clearing first keeps repeated runs idempotent: without it, mutagen
    # would accumulate duplicate APIC frames. clear() rather than delete()
    # so this works on a WAVE's in-memory ID3 too -- the save() that
    # follows rewrites the whole tag block on disk regardless.
    tags.clear()
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


def _write_id3(path: Path, ext: str, meta: TrackMeta,
               artwork: bytes | None) -> None:
    if ext == ".wav":
        container = WAVE(path)
        if container.tags is None:
            container.add_tags()
        _apply_id3(container.tags, meta, artwork)
        container.save(v2_version=3)
        return
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    _apply_id3(tags, meta, artwork)
    tags.save(path, v2_version=3)


def _read_id3(path: Path, ext: str) -> TrackMeta | None:
    try:
        if ext == ".wav":
            tags = WAVE(path).tags
        else:
            # mutagen's ID3() defaults to v2_version=4, which silently
            # upgrades old-style frames (TYER -> TDRC) on load regardless
            # of what's on disk. This file is v2.3, so read it as v2.3.
            tags = ID3(path, v2_version=3)
    except ID3NoHeaderError:
        return None
    if not tags or "TIT2" not in tags:
        return None

    def text(frame: str) -> str | None:
        return str(tags[frame].text[0]) if frame in tags else None

    track = text("TRCK")
    return TrackMeta(
        artist=text("TPE1") or "",
        title=text("TIT2") or "",
        album=text("TALB") or "",
        # TDRC as a fallback: a WAVE read can still hand back the upgraded
        # frame even though _write_id3 persists TYER.
        year=text("TYER") or text("TDRC"),
        genre=text("TCON"),
        track_number=int(track) if track and track.isdigit() else None,
    )


# --- Vorbis comments (FLAC, Ogg) ------------------------------------------

def _write_vorbis(path: Path, ext: str, meta: TrackMeta,
                  artwork: bytes | None) -> None:
    audio = FLAC(path) if ext == ".flac" else OggVorbis(path)
    audio.clear()
    if ext == ".flac":
        audio.clear_pictures()

    audio["TITLE"] = [meta.title]
    audio["ARTIST"] = [meta.artist]
    audio["ALBUM"] = [meta.album]
    audio["ALBUMARTIST"] = [meta.artist]
    if meta.year:
        audio["DATE"] = [meta.year]
    if meta.genre:
        audio["GENRE"] = [meta.genre]
    if meta.track_number is not None:
        audio["TRACKNUMBER"] = [str(meta.track_number)]

    if artwork:
        picture = Picture()
        picture.type = 3
        picture.mime = "image/jpeg"
        picture.desc = "Cover"
        picture.data = artwork
        if ext == ".flac":
            audio.add_picture(picture)
        else:
            audio["METADATA_BLOCK_PICTURE"] = [
                base64.b64encode(picture.write()).decode("ascii")
            ]

    audio.save()


def _read_vorbis(path: Path) -> TrackMeta | None:
    ext = Path(path).suffix.lower()
    audio = FLAC(path) if ext == ".flac" else OggVorbis(path)

    def first(key: str) -> str | None:
        # Vorbis keys are case-insensitive; mutagen exposes them lowercased.
        values = audio.get(key)
        return values[0] if values else None

    if not first("title"):
        return None

    track = first("tracknumber")
    if track and "/" in track:
        track = track.split("/", 1)[0]
    return TrackMeta(
        artist=first("artist") or "",
        title=first("title") or "",
        album=first("album") or "",
        year=first("date"),
        genre=first("genre"),
        track_number=int(track) if track and track.isdigit() else None,
    )


# --- MP4 atoms (M4A) -----------------------------------------------------

def _write_mp4(path: Path, meta: TrackMeta, artwork: bytes | None) -> None:
    audio = MP4(path)
    audio.clear()

    audio["\xa9nam"] = [meta.title]
    audio["\xa9ART"] = [meta.artist]
    audio["\xa9alb"] = [meta.album]
    audio["aART"] = [meta.artist]
    if meta.year:
        audio["\xa9day"] = [meta.year]
    if meta.genre:
        audio["\xa9gen"] = [meta.genre]
    if meta.track_number is not None:
        audio["trkn"] = [(meta.track_number, 0)]
    if artwork:
        audio["covr"] = [
            MP4Cover(artwork, imageformat=MP4Cover.FORMAT_JPEG)
        ]

    audio.save()


def _read_mp4(path: Path) -> TrackMeta | None:
    audio = MP4(path)

    def first(key: str):
        values = audio.get(key)
        return values[0] if values else None

    if not first("\xa9nam"):
        return None

    trkn = audio.get("trkn")
    track_number = trkn[0][0] if trkn and trkn[0] and trkn[0][0] else None
    return TrackMeta(
        artist=first("\xa9ART") or "",
        title=first("\xa9nam") or "",
        album=first("\xa9alb") or "",
        year=first("\xa9day"),
        genre=first("\xa9gen"),
        track_number=track_number,
    )
