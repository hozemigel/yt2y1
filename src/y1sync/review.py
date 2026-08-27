"""Ask the user to resolve an ambiguous identification."""

import re
from collections.abc import Sequence
from itertools import groupby
from pathlib import Path

from .models import Candidate
from .ranking import DEPRIORITISED_TYPES, rank_candidates, recording_identity

# How many derivative releases (compilations, live albums, remixes) of one
# recording to list individually. A popular song can have appeared on
# dozens of compilations -- one real case ran to 17 -- and once the
# original is shown, the rest are interchangeable for tagging purposes:
# listing all of them just buries whatever comes after in the list.
MAX_DERIVATIVE_SHOWN = 2


def _title_words(text: str) -> set[str]:
    return set(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _matches_filename(title: str, stem: str) -> bool:
    """Rough check: does a candidate's title show up in the filename?

    Half the title's words is enough — filenames often carry extra noise
    (features, remix tags) the title itself doesn't have, so requiring a
    full match would flag those as false mismatches.
    """
    title_words = _title_words(title)
    if not title_words:
        return True
    return len(title_words & _title_words(stem)) / len(title_words) >= 0.5


def _describe(candidate: Candidate) -> str:
    parts = [f"{candidate.meta.artist} - {candidate.meta.title}"]
    parts.append(f"[{candidate.meta.album}]")
    if candidate.meta.year:
        parts.append(f"({candidate.meta.year})")
    if candidate.secondary_types:
        parts.append(f"<{', '.join(candidate.secondary_types)}>")
    return " ".join(parts)


def _is_derivative(candidate: Candidate) -> bool:
    return bool(set(candidate.secondary_types) & DEPRIORITISED_TYPES)


def _cap_derivatives(group: list[Candidate]) -> tuple[list[Candidate], int]:
    """Keep every non-derivative release; cap derivative ones at MAX_DERIVATIVE_SHOWN.

    Ranking already puts non-derivative releases first, so this only ever
    trims off the tail of compilations, live albums and remixes -- never
    the original a group's first entries represent.
    """
    shown = []
    derivative_shown = 0
    hidden = 0
    for candidate in group:
        if _is_derivative(candidate):
            if derivative_shown >= MAX_DERIVATIVE_SHOWN:
                hidden += 1
                continue
            derivative_shown += 1
        shown.append(candidate)
    return shown, hidden


def choose_candidate(
    path: Path,
    candidates: Sequence[Candidate],
    input_fn=input,
    output_fn=print,
) -> Candidate | None:
    """Present ranked options and return the user's choice.

    Returns None when the user skips or there is nothing to choose from.
    Options are shown best-first so pressing Enter takes the original
    album rather than a compilation.
    """
    if not candidates:
        return None

    ranked = rank_candidates(candidates)
    output_fn(f"\n{Path(path).name}")

    stem = Path(path).stem
    titles = {candidate.meta.title for candidate in ranked if candidate.meta.title}
    if titles and not any(_matches_filename(title, stem) for title in titles):
        output_fn(
            f'  Fingerprint says this is "{ranked[0].meta.title}", which does not '
            "match the filename. Listen to the track before choosing — the file "
            "may be mislabeled."
        )

    # Grouped by recording (ranking already keeps each one's releases
    # contiguous), with a per-group cap on how many derivative releases
    # get listed. Numbering only ever covers what actually prints, so a
    # capped-off compilation is not a choice the user loses -- it was
    # never meaningfully different from the one or two shown for tagging
    # purposes.
    displayed: list[Candidate] = []
    for group_index, (_, group_iter) in enumerate(groupby(ranked, key=recording_identity)):
        if group_index > 0:
            output_fn("")
        shown, hidden = _cap_derivatives(list(group_iter))
        for candidate in shown:
            displayed.append(candidate)
            output_fn(f"  {len(displayed)}. {_describe(candidate)}")
        if hidden:
            output_fn(f"      + {hidden} more compilation(s) of the same recording, not shown")
    ranked = displayed

    while True:
        reply = input_fn("Type a number, Enter for [1], or 's' to skip: ").strip().lower()
        if reply == "s":
            return None
        if reply == "":
            return ranked[0]
        if reply.isdigit() and 1 <= int(reply) <= len(ranked):
            return ranked[int(reply) - 1]
        output_fn("Enter a listed number, or 's' to skip.")
