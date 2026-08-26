# src/y1sync/artwork.py
"""Cover art download, cached on disk by URL."""

import hashlib
from pathlib import Path

import requests

from .models import TrackMeta

ITUNES_ENDPOINT = "https://itunes.apple.com/search"
TIMEOUT = 20


def artwork_url_for(meta: TrackMeta, session=None) -> str | None:
    """Find a cover art URL for a track that arrived without one.

    AcoustID and MusicBrainz return no artwork, so tracks identified by
    fingerprint — the primary path — need the album looked up on iTunes
    to get a picture.
    """
    http = session or requests
    term = f"{meta.artist} {meta.album}".strip()
    if not term:
        return None
    try:
        response = http.get(
            ITUNES_ENDPOINT,
            params={"term": term, "entity": "album", "limit": 1},
            timeout=TIMEOUT,
        )
    except Exception:
        return None
    if not response.ok:
        return None
    results = response.json().get("results") or []
    if not results:
        return None
    url = results[0].get("artworkUrl100") or ""
    return url.replace("100x100bb", "600x600bb") or None


def fetch_artwork(url: str | None, cache_dir: Path, session=None) -> bytes | None:
    """Download cover art, returning None if unavailable.

    Missing artwork is not an error: a track with correct tags and no
    picture is still a good result.
    """
    if not url:
        return None

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.jpg"
    if cached.exists():
        return cached.read_bytes()

    http = session or requests
    try:
        response = http.get(url, timeout=TIMEOUT)
    except Exception:
        return None
    if not response.ok or not response.content:
        return None

    cached.write_bytes(response.content)
    return response.content
