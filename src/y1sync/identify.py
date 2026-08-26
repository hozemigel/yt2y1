"""Identify a track: by audio fingerprint first, by filename as a fallback."""

import re
import subprocess
from pathlib import Path

import requests

from .models import Candidate, TrackMeta

ITUNES_ENDPOINT = "https://itunes.apple.com/search"
ACOUSTID_ENDPOINT = "https://api.acoustid.org/v2/lookup"
TIMEOUT = 15

# Debris that YouTube rips leave in filenames.
# The \b after each alternation is load-bearing: without it "audio"
# matches inside "Audioslave", so "Radioactive (Audioslave Cover).mp3"
# is stripped to "Radioactive" and a cover gets queried as the original
# recording -- the exact misidentification this tool exists to prevent.
NOISE_PATTERN = re.compile(
    r"\((?:official|lyrics?|audio|video|music|lyric)\b[^)]*\)"
    r"|\[[^\]]*\b(?:official|lyrics?|audio|video)\b[^\]]*\]",
    re.IGNORECASE,
)


def guess_query_from_filename(path: Path) -> str:
    """Turn a messy filename into a plausible search query."""
    stem = Path(path).stem
    stem = NOISE_PATTERN.sub(" ", stem)
    stem = stem.replace(" - ", " ")
    return re.sub(r"\s+", " ", stem).strip(" -")


def parse_itunes_response(payload: dict) -> list[Candidate]:
    """Convert an iTunes Search response into candidates.

    These are filename-derived guesses, so they are marked source
    "itunes" and always routed through review.
    """
    candidates = []
    for item in payload.get("results", []):
        release_date = (item.get("releaseDate") or "")[:10] or None
        artwork = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
        candidates.append(Candidate(
            meta=TrackMeta(
                artist=item.get("artistName", ""),
                title=item.get("trackName", ""),
                album=item.get("collectionName", ""),
                year=(release_date or "")[:4] or None,
                genre=item.get("primaryGenreName"),
                track_number=item.get("trackNumber"),
            ),
            confidence=0.0,
            source="itunes",
            release_group_type="Album",
            release_status="Official",
            release_date=release_date,
            artwork_url=artwork or None,
        ))
    return candidates


def _format_date(date: dict) -> str | None:
    """MusicBrainz dates may carry only a year, or only a year and month."""
    if not date or "year" not in date:
        return None
    return "{:04d}-{:02d}-{:02d}".format(
        date["year"], date.get("month", 1), date.get("day", 1)
    )


def parse_acoustid_response(payload: dict, score: float | None = None) -> list[Candidate]:
    """Convert an AcoustID lookup into one candidate per release group.

    Each result carries its own score. `score` overrides that only when a
    caller has a better figure; it is not a default applied to every
    result, or a weak second match would inherit a strong first one's
    confidence and could then be auto-applied.
    """
    candidates = []
    for result in payload.get("results", []):
        result_score = score if score is not None else result.get("score", 0.0)
        for recording in result.get("recordings", []):
            artists = recording.get("artists") or [{}]
            artist = artists[0].get("name", "")
            title = recording.get("title", "")
            for group in recording.get("releasegroups", []):
                releases = group.get("releases") or [{}]
                first = releases[0]
                release_date = _format_date(first.get("date") or {})
                candidates.append(Candidate(
                    meta=TrackMeta(
                        artist=artist,
                        title=title,
                        album=group.get("title", ""),
                        year=(release_date or "")[:4] or None,
                    ),
                    confidence=result_score,
                    source="acoustid",
                    release_group_type=group.get("type"),
                    secondary_types=tuple(group.get("secondarytypes") or ()),
                    release_status=first.get("status"),
                    release_date=release_date,
                ))
    return candidates


def fingerprint(path: Path) -> tuple[int, str] | None:
    """Return (duration, fingerprint) from chromaprint's fpcalc, or None."""
    try:
        proc = subprocess.run(
            ["fpcalc", "-json", str(path)],
            capture_output=True, text=True, check=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    import json
    data = json.loads(proc.stdout)
    return int(data["duration"]), data["fingerprint"]


def identify(path: Path, api_key: str | None = None, session=None) -> list[Candidate]:
    """Identify a track, preferring the fingerprint route.

    Returns candidates. It never decides which one is correct — that is
    ranking.decide()'s job.
    """
    http = session or requests
    if api_key:
        printed = fingerprint(path)
        if printed:
            duration, fp = printed
            response = http.get(ACOUSTID_ENDPOINT, params={
                "client": api_key, "duration": duration, "fingerprint": fp,
                "meta": "recordings+releasegroups+compress", "format": "json",
            }, timeout=TIMEOUT)
            if response.ok:
                payload = response.json()
                results = payload.get("results") or []
                if results:
                    parsed = parse_acoustid_response(payload)
                    if parsed:
                        return parsed

    response = http.get(ITUNES_ENDPOINT, params={
        "term": guess_query_from_filename(path), "entity": "song", "limit": 5,
    }, timeout=TIMEOUT)
    if not response.ok:
        return []
    return parse_itunes_response(response.json())
