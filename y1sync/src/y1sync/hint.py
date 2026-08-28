"""Load the sidecar yt2mp3 leaves next to a download.

When an audio fingerprint comes back empty, identify() would otherwise
guess from the filename. If yt2mp3 fetched the file it also wrote what
YouTube said the track was (see yt2mp3/metadata.py), and for the
lesser-known tracks a fingerprint tends to miss that is a far better
starting point. This reads that sidecar defensively: anything unreadable,
malformed, or with nothing to search on is simply "no hint", and
identify() carries on exactly as before.
"""

import json
from dataclasses import dataclass
from pathlib import Path

SIDECAR_SUFFIX = ".yt2mp3.json"


@dataclass(frozen=True)
class YtHint:
    """What YouTube said a track was. Every field is optional."""

    artist: str | None = None
    track: str | None = None
    album: str | None = None
    year: str | None = None
    video_title: str | None = None
    url: str | None = None

    @property
    def usable(self) -> bool:
        """True when there is something to search on rather than nothing."""
        return bool(self.artist or self.track or self.video_title)


def _sidecar_for(mp3_path: Path) -> Path:
    mp3 = Path(mp3_path)
    return mp3.with_name(mp3.stem + SIDECAR_SUFFIX)


def load_hint(mp3_path: Path) -> YtHint | None:
    """The YtHint for an MP3, or None when there is no usable sidecar."""
    try:
        raw = json.loads(_sidecar_for(mp3_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    def field(name: str) -> str | None:
        value = raw.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    hint = YtHint(
        artist=field("artist"),
        track=field("track"),
        album=field("album"),
        year=field("year"),
        video_title=field("video_title"),
        url=field("url"),
    )
    return hint if hint.usable else None
