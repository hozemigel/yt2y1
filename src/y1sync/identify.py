"""Identify a track: by audio fingerprint first, by filename as a fallback."""

import re
import subprocess
import time
from pathlib import Path

import requests

from .models import Candidate, TrackMeta

ITUNES_ENDPOINT = "https://itunes.apple.com/search"
ACOUSTID_ENDPOINT = "https://api.acoustid.org/v2/lookup"
MUSICBRAINZ_ENDPOINT = "https://musicbrainz.org/ws/2/recording"

# MusicBrainz asks unauthenticated clients for one request per second and
# a User-Agent that identifies the application.
MUSICBRAINZ_USER_AGENT = "y1sync/0.1 (https://github.com/lukamilicevic/y1sync)"
MUSICBRAINZ_RATE_LIMIT = 1.1

# How many distinct recordings from one AcoustID hit to expand. Each costs
# a rate-limited MusicBrainz request, and past the first few the matches
# are usually the same recording on yet another release.
MAX_RECORDINGS_EXPANDED = 3

# How far a recording's stated length may sit from the file's before it is
# treated as different audio. Pressings of one recording differ by a second
# or two; an edit or a remix differs by far more.
DURATION_TOLERANCE = 8.0
TIMEOUT = 15

# How far a result's score may trail the top one and still be expanded.
# AcoustID sometimes splits one file's true match across two results with
# near-identical scores -- e.g. 0.9767 and 0.9747 -- each naming a
# different recording. Looking only at the single top-scored result then
# silently drops the right answer if it landed in the second one.
SCORE_TOLERANCE = 0.02

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


class AcoustIDKeyRejected(Exception):
    """AcoustID refused the configured key.

    Raised rather than swallowed because the alternative is worse than an
    error: identification silently drops to guessing from the filename,
    which is the failure mode this whole tool exists to prevent, while the
    user believes fingerprinting is working.
    """


# AcoustID error codes that mean the key itself is unusable, so no
# amount of retrying or moving to the next file will help.
_KEY_ERROR_CODES = {4, 6}


def _raise_if_key_rejected(payload: dict) -> None:
    """Turn AcoustID's "invalid API key" into a hard stop."""
    error = payload.get("error") or {}
    if error.get("code") in _KEY_ERROR_CODES:
        raise AcoustIDKeyRejected(
            f"AcoustID rejected the configured key: {error.get('message', 'invalid')}. "
            "Fingerprinting is unavailable, so tracks would be identified from "
            "their filenames alone. Get an application key at "
            "https://acoustid.org/new-application and set acoustid_key in "
            "~/.config/y1sync/config.toml"
        )


def musicbrainz_releases(recording_id: str, session=None) -> list[dict]:
    """Look up one recording's releases, with the types ranking needs.

    AcoustID identifies *which recording* a file holds but returns no
    release information, so this second hop is what lets the tool tell an
    original album from a compilation.
    """
    http = session or requests
    try:
        response = http.get(
            f"{MUSICBRAINZ_ENDPOINT}/{recording_id}",
            params={"inc": "releases+release-groups+artists", "fmt": "json"},
            headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
            timeout=TIMEOUT,
        )
    except Exception:
        return []
    if not getattr(response, "ok", False):
        return []
    try:
        return response.json().get("releases") or []
    except ValueError:
        return []


def candidates_from_musicbrainz(
    recording: dict, releases: list[dict], score: float
) -> list[Candidate]:
    """Build one candidate per release of a recording."""
    artists = recording.get("artists") or [{}]
    artist = artists[0].get("name", "")
    title = recording.get("title", "")

    candidates = []
    for release in releases:
        group = release.get("release-group") or {}
        date = release.get("date") or group.get("first-release-date") or ""
        candidates.append(Candidate(
            meta=TrackMeta(
                artist=artist,
                title=title,
                album=release.get("title", ""),
                year=date[:4] or None,
            ),
            confidence=score,
            source="acoustid",
            release_group_type=group.get("primary-type"),
            secondary_types=tuple(group.get("secondary-types") or ()),
            release_status=release.get("status"),
            release_date=date or None,
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


def _duration_rank(recording: dict, duration: float | None) -> tuple[int, float]:
    """Sort key placing recordings whose length matches the file first."""
    stated = recording.get("duration")
    if duration is None or stated is None:
        return (1, 0.0)
    delta = abs(float(stated) - duration)
    return (0 if delta <= DURATION_TOLERANCE else 1, delta)


def _expand_acoustid(payload: dict, http, duration: float | None = None) -> list[Candidate]:
    """Turn an AcoustID hit into candidates, via MusicBrainz for releases.

    AcoustID names the recording; MusicBrainz says which releases carry
    it and of what type. Without the second hop every candidate would
    lack the release data the ranking rules are built on, and an original
    album would be indistinguishable from a compilation.
    """
    results = payload.get("results") or []
    if not results:
        return []

    # Pool recordings from every result within SCORE_TOLERANCE of the best
    # score, not just the top result, so a true match does not vanish for
    # having landed in a near-tied second cluster. Each recording keeps the
    # highest score it appeared under.
    top_score = max(result.get("score", 0.0) for result in results)
    scored: dict[str, tuple[dict, float]] = {}
    for result in results:
        score = result.get("score", 0.0)
        if score < top_score - SCORE_TOLERANCE:
            continue
        for recording in result.get("recordings") or []:
            recording_id = recording.get("id")
            if not recording_id:
                continue
            best_so_far = scored.get(recording_id)
            if best_so_far is None or score > best_so_far[1]:
                scored[recording_id] = (recording, score)

    # AcoustID returns equally-scored recordings in no dependable order, so
    # expanding "the first three" gave a different answer run to run. Length
    # settles it: a 123-second remix is not the 156-second track on disk,
    # however well its fingerprint matches.
    recordings = sorted(
        (recording for recording, _ in scored.values()),
        key=lambda r: _duration_rank(r, duration),
    )

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for recording in recordings[:MAX_RECORDINGS_EXPANDED]:
        recording_id = recording.get("id")
        if not recording_id or recording_id in seen:
            continue
        if seen:
            # MusicBrainz asks for one request per second.
            time.sleep(MUSICBRAINZ_RATE_LIMIT)
        seen.add(recording_id)
        releases = musicbrainz_releases(recording_id, http)
        score = scored[recording_id][1]
        candidates.extend(candidates_from_musicbrainz(recording, releases, score))

    return candidates


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
            # meta goes as repeated parameters: requests percent-encodes a
            # "+" inside a value, and AcoustID then reads the whole string
            # as one unknown meta name and silently returns no recordings.
            response = http.get(ACOUSTID_ENDPOINT, params=[
                ("client", api_key), ("duration", duration), ("fingerprint", fp),
                ("format", "json"), ("meta", "recordings"), ("meta", "compress"),
            ], timeout=TIMEOUT)
            if response.ok:
                payload = response.json()
                if payload.get("status") == "error":
                    _raise_if_key_rejected(payload)
                parsed = _expand_acoustid(payload, http, duration)
                if parsed:
                    return parsed
            else:
                # A 4xx carries AcoustID's own error body; read it before
                # deciding this was merely a transient failure.
                try:
                    _raise_if_key_rejected(response.json())
                except ValueError:
                    pass

    response = http.get(ITUNES_ENDPOINT, params={
        "term": guess_query_from_filename(path), "entity": "song", "limit": 5,
    }, timeout=TIMEOUT)
    if not response.ok:
        return []
    return parse_itunes_response(response.json())
