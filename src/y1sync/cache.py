"""Cache identification results by audio content, not by filename."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .models import Candidate, TrackMeta

_CHUNK = 1024 * 1024


def content_hash(path: Path) -> str:
    """SHA-256 of the file's bytes, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ContentCache:
    """Stores candidate lists keyed by content hash.

    Keying on content rather than path means renaming a file — which this
    tool does routinely — never discards its cached identification.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, path: Path) -> Path:
        return self.root / f"{content_hash(path)}.json"

    def get(self, path: Path) -> list[Candidate] | None:
        entry = self._path_for(path)
        if not entry.exists():
            return None
        raw = json.loads(entry.read_text(encoding="utf-8"))
        return [
            Candidate(
                meta=TrackMeta(**item["meta"]),
                confidence=item["confidence"],
                source=item["source"],
                release_group_type=item["release_group_type"],
                secondary_types=tuple(item["secondary_types"]),
                release_status=item["release_status"],
                release_date=item["release_date"],
                artwork_url=item["artwork_url"],
            )
            for item in raw
        ]

    def put(self, path: Path, candidates: list[Candidate]) -> None:
        payload = []
        for cand in candidates:
            item = asdict(cand)
            item["secondary_types"] = list(cand.secondary_types)
            payload.append(item)
        self._path_for(path).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
