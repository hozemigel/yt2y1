"""Cache identification results by audio content, not by filename."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mutagen import MutagenError
from mutagen.mp3 import MP3

from .models import Candidate, TrackMeta

_CHUNK = 1024 * 1024

# An ID3v1 tag is a fixed 128-byte trailer introduced by "TAG".
_ID3V1_SIZE = 128
_ID3V1_MAGIC = b"TAG"


def _audio_bounds(path: Path) -> tuple[int, int]:
    """Return (start, end) byte offsets of the audio payload.

    mutagen reports where the first MPEG frame begins, which is exactly
    where any ID3v2 tag ends. Anything this function cannot parse — a
    truncated file, a stub written by a test — is hashed whole.
    """
    size = path.stat().st_size
    try:
        start = MP3(path).info.frame_offset
    except (MutagenError, OSError, ValueError):
        return 0, size

    end = size
    if end - start >= _ID3V1_SIZE:
        with open(path, "rb") as handle:
            handle.seek(end - _ID3V1_SIZE)
            if handle.read(len(_ID3V1_MAGIC)) == _ID3V1_MAGIC:
                end -= _ID3V1_SIZE
    return start, end


def content_hash(path: Path) -> str:
    """SHA-256 of the file's audio payload, excluding its ID3 tags.

    The tag region has to be excluded because write_tags() embeds frames
    into the same file the cache keys on. Hashing the whole file would
    change the key on every successful scan, so the second run would miss
    every entry, re-query the network for every track and re-ask every
    question the user has already answered.
    """
    path = Path(path)
    start, end = _audio_bounds(path)
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = end - start
        while remaining > 0:
            chunk = handle.read(min(_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CachedIdentification:
    """What a previous run learned about one file."""

    candidates: list[Candidate] = field(default_factory=list)
    #: The candidate that was applied, once the question has been answered.
    choice: Candidate | None = None


def _to_json(candidate: Candidate) -> dict:
    item = asdict(candidate)
    item["secondary_types"] = list(candidate.secondary_types)
    return item


def _from_json(item: dict) -> Candidate:
    return Candidate(
        meta=TrackMeta(**item["meta"]),
        confidence=item["confidence"],
        source=item["source"],
        release_group_type=item["release_group_type"],
        secondary_types=tuple(item["secondary_types"]),
        release_status=item["release_status"],
        release_date=item["release_date"],
        # .get: entries cached before Candidate carried a stated duration.
        stated_duration=item.get("stated_duration"),
        artwork_url=item["artwork_url"],
    )


class ContentCache:
    """Stores identifications keyed by audio content hash.

    Keying on content rather than path means renaming a file — which this
    tool does routinely — never discards its cached identification.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, path: Path) -> Path:
        return self.root / f"{content_hash(path)}.json"

    def get(self, path: Path) -> CachedIdentification | None:
        entry = self._path_for(path)
        if not entry.exists():
            return None
        try:
            raw = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        # Entries written before choices were recorded are bare lists.
        if isinstance(raw, list):
            return CachedIdentification([_from_json(item) for item in raw])
        choice = raw.get("choice")
        return CachedIdentification(
            candidates=[_from_json(item) for item in raw.get("candidates", [])],
            choice=_from_json(choice) if choice else None,
        )

    def put(
        self,
        path: Path,
        candidates: list[Candidate],
        choice: Candidate | None = None,
    ) -> None:
        payload = {
            "candidates": [_to_json(c) for c in candidates],
            "choice": _to_json(choice) if choice is not None else None,
        }
        self._path_for(path).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
