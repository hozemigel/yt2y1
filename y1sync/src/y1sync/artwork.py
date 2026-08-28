# src/y1sync/artwork.py
"""Cover art download, cached on disk by URL."""

import hashlib
import re
from pathlib import Path

import requests

from .models import TrackMeta

ITUNES_ENDPOINT = "https://itunes.apple.com/search"
TIMEOUT = 20

# A trailing qualifier like "(Radio Edit)", "(House Remix)" or "(Live
# Session)" describes a specific version, not a distinct release with its
# own iTunes listing -- searching with it still attached usually finds
# nothing, even though the underlying song has an official cover on file.
# Only the *trailing* parenthetical is stripped: a title genuinely
# containing "(...)" earlier on (a subtitle, a featured artist) is left
# alone rather than mangled on the guess that it's the same kind of noise.
TRAILING_QUALIFIER = re.compile(r"\s*\([^()]*\)\s*$")


def _itunes_artwork(term: str, http) -> str | None:
    if not term:
        return None
    try:
        response = http.get(
            ITUNES_ENDPOINT,
            params={"term": term, "entity": "album", "limit": 1},
            timeout=TIMEOUT,
        )
        if not response.ok:
            return None
        results = response.json().get("results") or []
        if not results or not isinstance(results[0], dict):
            return None
        url = results[0].get("artworkUrl100") or ""
    except Exception:
        return None
    return url.replace("100x100bb", "600x600bb") or None


def artwork_url_for(meta: TrackMeta, session=None) -> str | None:
    """Find a cover art URL for a track that arrived without one.

    AcoustID and MusicBrainz return no artwork, so tracks identified by
    fingerprint — the primary path — need iTunes looked up to get a
    picture. Tried in order, each one only when the previous finds
    nothing:

    1. artist + album -- skipped when there is no album, rather than
       searching on the artist's name alone. Found on a real track with
       no album: "Electric Youth" by itself matched Debbie Gibson's 1989
       album of the same name -- an unrelated artist with an unrelated
       cover, nothing to do with the actual track.
    2. artist + title. Found on a real track: ranking's only candidate
       was a radio promo compilation iTunes had never heard of, so the
       album search came up empty and the file was tagged with no
       artwork at all — searching by title alone found the same song
       under its real single release.
    3. artist + title with a trailing qualifier stripped -- "(Radio
       Edit)", "(House Remix)", "(Live Session)" and the like describe a
       specific version, not a release with its own iTunes listing, so
       searching with one still attached usually finds nothing even
       though the underlying song has an official cover on file.
    """
    http = session or requests
    terms = []
    if meta.album:
        terms.append(f"{meta.artist} {meta.album}".strip())
    if meta.title:
        terms.append(f"{meta.artist} {meta.title}".strip())
        stripped_title = TRAILING_QUALIFIER.sub("", meta.title).strip()
        if stripped_title and stripped_title != meta.title:
            terms.append(f"{meta.artist} {stripped_title}".strip())
    for term in terms:
        url = _itunes_artwork(term, http)
        if url:
            return url
    return None


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
