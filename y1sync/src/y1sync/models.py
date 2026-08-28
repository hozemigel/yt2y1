"""Core data structures shared across the package."""

from dataclasses import dataclass


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
    #: The matched recording's own stated length in seconds, when the
    #: source gives one. An AcoustID fingerprint only covers a track's
    #: first ~120 seconds, so a short edit can match a full-length
    #: recording; comparing this against the file is what catches that.
    #: None when the source reports no duration.
    stated_duration: float | None = None
    artwork_url: str | None = None
