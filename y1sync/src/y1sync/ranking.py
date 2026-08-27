"""Ranking releases, and deciding when to ask the user.

A fingerprint tells you which recording a file contains. It cannot tell
you which release the user wants it filed under: the same recording may
appear on the original album, a compilation, a remaster and a deluxe
edition. This module ranks the original first and, when there is any real
choice to make, hands the decision back to the user.
"""

from collections.abc import Sequence

from .models import Candidate

# Secondary release types that indicate a derivative release.
DEPRIORITISED_TYPES = {"Compilation", "Live", "Remix", "DJ-mix"}

# Sorts after any real date, so undated releases fall to the bottom.
_NO_DATE = "9999-99-99"

# Typographic variants MusicBrainz submissions are inconsistent about.
# Found on a real track: the same single was catalogued twice as "It
# Ain't Me" and "It Ain’t Me", differing only in apostrophe style, and
# compared unequal -- dedup kept both as if they were different releases.
_PUNCTUATION_VARIANTS = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
})


def _normalize(text: str) -> str:
    """Fold case and typographic punctuation so near-identical text compares equal."""
    return text.casefold().translate(_PUNCTUATION_VARIANTS)


def _sort_key(candidate: Candidate) -> tuple:
    is_album = candidate.release_group_type == "Album"
    is_derivative = bool(set(candidate.secondary_types) & DEPRIORITISED_TYPES)
    is_official = candidate.release_status == "Official"
    # False sorts before True, so negate the qualities we want first.
    #
    # Being derivative outranks not being an Album, and the order matters:
    # a compilation is still an "Album", so testing is_album first let a
    # German hits compilation beat the original single a track was
    # actually released on. Nothing derivative belongs at the top,
    # whatever its primary type says.
    return (
        is_derivative,
        not is_album,
        not is_official,
        candidate.release_date or _NO_DATE,
    )


def _identity(candidate: Candidate) -> tuple[str, str, str]:
    """What makes two candidates the same choice, as far as a user cares."""
    meta = candidate.meta
    return (_normalize(meta.artist), _normalize(meta.title), _normalize(meta.album))


def recording_identity(candidate: Candidate) -> tuple[str, str]:
    """What makes two candidates releases of the same recording."""
    meta = candidate.meta
    return (_normalize(meta.artist), _normalize(meta.title))


def dedupe_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Collapse candidates that name the same artist, title and album.

    MusicBrainz models every pressing as its own release, so one album can
    arrive a dozen times over -- differing only in country or catalogue
    number, which a user choosing a tag cannot act on. Input order decides
    which survives, so rank before deduping and the best one is kept.
    """
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for candidate in candidates:
        key = _identity(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Order candidates best-first: original official albums, earliest wins.

    Candidates can span more than one recording -- a near-tied AcoustID
    match can name two different songs (see identify._expand_acoustid).
    Pooling every release across recordings by quality alone scattered a
    lone compilation for the true recording between unrelated albums for
    the wrong one, with nothing marking the boundary. Each recording's
    releases are kept together instead, ordered highest-confidence
    recording first -- still a suggestion, not a verdict, since AcoustID
    scores this close (a few thousandths) are close to a tie.

    Duplicates are collapsed, so a release that exists in ten pressings
    offers one choice rather than ten identical-looking ones.
    """
    best_confidence: dict[tuple[str, str], float] = {}
    for candidate in candidates:
        identity = recording_identity(candidate)
        best_confidence[identity] = max(
            best_confidence.get(identity, candidate.confidence), candidate.confidence
        )

    def key(candidate: Candidate) -> tuple:
        return (-best_confidence[recording_identity(candidate)], _sort_key(candidate))

    return dedupe_candidates(sorted(candidates, key=key))


def decide(
    candidates: Sequence[Candidate], threshold: float = 0.90
) -> tuple[Candidate | None, bool]:
    """Return (pick, needs_review).

    When needs_review is True the pick is a suggestion to show the user,
    not a decision. Automatic application requires all three of:
    a fingerprint source, confidence at or above the threshold, and
    exactly one candidate release.
    """
    if not candidates:
        return None, True

    ranked = rank_candidates(candidates)
    top = ranked[0]

    if len(ranked) > 1:
        return top, True
    if top.source != "acoustid":
        return top, True
    if top.confidence < threshold:
        return top, True
    return top, False
