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


def _sort_key(candidate: Candidate) -> tuple:
    is_album = candidate.release_group_type == "Album"
    is_derivative = bool(set(candidate.secondary_types) & DEPRIORITISED_TYPES)
    is_official = candidate.release_status == "Official"
    # False sorts before True, so negate the qualities we want first.
    return (
        not is_album,
        is_derivative,
        not is_official,
        candidate.release_date or _NO_DATE,
    )


def rank_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Order candidates best-first: original official albums, earliest wins."""
    return sorted(candidates, key=_sort_key)


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
