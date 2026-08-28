"""Write a sidecar recording what YouTube said a download was.

yt-dlp hands ``download()`` a fully populated ``info_dict`` -- artist,
track, album, release year, the "Provided to YouTube by" block parsed out
of the description -- and yt2mp3 otherwise keeps only the path of the MP3
it wrote. For a track from a YouTube Music "- Topic" channel that
metadata is usually clean and often exactly right, and it is precisely
what y1sync needs when an audio fingerprint comes back empty (obscure and
independent tracks, mostly). This drops it beside the MP3 as
``<stem>.yt2mp3.json`` for y1sync to pick up; y1sync ignores files it
cannot read or parse, so a partial or missing sidecar costs nothing.
"""

import json
from pathlib import Path

SIDECAR_SUFFIX = ".yt2mp3.json"
SCHEMA_VERSION = 1


def sidecar_path(mp3_path: str | Path) -> Path:
    """Where the sidecar for a given MP3 lives: beside it, same stem."""
    mp3 = Path(mp3_path)
    return mp3.with_name(mp3.stem + SIDECAR_SUFFIX)


def _clean(value) -> str | None:
    """A trimmed non-empty string, or None. A list/tuple joins on ", "."""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v).strip() for v in value if str(v).strip())
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_sidecar(info: dict) -> dict:
    """The JSON body for one download's sidecar. Empty fields are omitted;
    ``schema`` and ``tool`` are always present."""
    year = _clean(info.get("release_year"))
    if not year:
        release_date = _clean(info.get("release_date"))  # yt-dlp gives "YYYYMMDD"
        year = release_date[:4] if release_date else None

    fields = {
        "url": _clean(info.get("webpage_url")),
        "video_title": _clean(info.get("title")),
        "channel": _clean(info.get("channel") or info.get("uploader")),
        "artist": _clean(info.get("artist")),
        "track": _clean(info.get("track")),
        "album": _clean(info.get("album")),
        "year": year,
    }
    body = {"schema": SCHEMA_VERSION, "tool": "yt2mp3"}
    body.update({key: value for key, value in fields.items() if value is not None})
    return body


def write_sidecar(info: dict, mp3_path: str | Path) -> None:
    """Write the sidecar for a finished download. Never raises: a sidecar
    that could not be written must not turn a successful download into a
    reported failure -- y1sync just falls back to its filename guess."""
    try:
        sidecar_path(mp3_path).write_text(
            json.dumps(build_sidecar(info), ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
