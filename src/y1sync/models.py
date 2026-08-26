"""Core data structures shared across the package."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrackMeta:
    """The metadata that will be written to a file's ID3 tags."""

    artist: str
    title: str
    album: str
    year: str | None = None
    genre: str | None = None
    track_number: int | None = None


@dataclass(frozen=True)
class Candidate:
    """One possible identification of a track, with everything needed to rank it.

    Identification never picks a winner. It returns these, and ranking.py
    decides whether one is good enough to apply without asking.
    """

    meta: TrackMeta
    confidence: float
    source: str
    release_group_type: str | None = None
    secondary_types: tuple[str, ...] = ()
    release_status: str | None = None
    release_date: str | None = None
    artwork_url: str | None = None
