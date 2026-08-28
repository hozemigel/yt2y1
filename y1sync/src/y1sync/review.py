"""Ask the user to resolve an ambiguous identification."""

import re
from collections.abc import Sequence
from itertools import groupby
from pathlib import Path

from .models import Candidate
from .ranking import (
    DEPRIORITISED_TYPES,
    DURATION_MISMATCH_LIMIT,
    rank_candidates,
    recording_identity,
)

# How many derivative releases (compilations, live albums, remixes) of one
# recording to list individually. A popular song can have appeared on
# dozens of compilations -- one real case ran to 17 -- and once the
# original is shown, the rest are interchangeable for tagging purposes:
# listing all of them just buries whatever comes after in the list.
MAX_DERIVATIVE_SHOWN = 2


def _mmss(seconds: float) -> str:
    """Seconds as m:ss, for a length the user can compare against the track."""
    total = round(seconds)
    return f"{total // 60}:{total % 60:02d}"


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


def _group_header(candidates: list[Candidate]) -> str:
    """The artist and title every candidate in a group shares.

    Printed once above the group instead of on every row -- repeating it
    per row was the single biggest source of clutter in a list that can
    run to a dozen near-identical-looking entries.
    """
    first = candidates[0]
    return f"{first.meta.artist} — {first.meta.title}"


def _row(candidate: Candidate, album_width: int) -> str:
    """One release within a group: just the part that varies -- album, year, type."""
    parts = [candidate.meta.album.ljust(album_width)]
    if candidate.meta.year:
        parts.append(candidate.meta.year)
    if candidate.secondary_types:
        parts.append(f"({', '.join(t.lower() for t in candidate.secondary_types)})")
    return "  ".join(parts).rstrip()


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
    file_duration: float | None = None,
) -> Candidate | None:
    """Present ranked options and return the user's choice.

    Returns None when the user skips or there is nothing to choose from.
    Options are shown best-first so pressing Enter takes the original
    album rather than a compilation. ``file_duration`` is the track's own
    length in seconds, used only to warn when it is far from the matched
    recording's.
    """
    if not candidates:
        return None

    ranked = rank_candidates(candidates)

    # Grouped by recording (ranking already keeps each one's releases
    # contiguous), with a per-group cap on how many derivative releases
    # get listed. Numbering only ever covers what actually prints, so a
    # capped-off compilation is not a choice the user loses -- it was
    # never meaningfully different from the one or two shown for tagging
    # purposes.
    groups = [
        _cap_derivatives(list(group_iter))
        for _, group_iter in groupby(ranked, key=recording_identity)
    ]
    total_shown = sum(len(shown) for shown, _hidden in groups)

    header = "One match found for:" if total_shown == 1 else "Multiple matches for:"
    output_fn(f"\n{header}")
    output_fn(f"  {Path(path).name}")

    if ranked and ranked[0].source == "youtube":
        top = ranked[0]
        detail = ", ".join(part for part in (top.meta.album, top.meta.year) if part)
        suffix = f" ({detail})" if detail else ""
        output_fn(
            f"  From the YouTube page: {top.meta.artist} — {top.meta.title}{suffix}"
        )

    stem = Path(path).stem
    titles = {candidate.meta.title for candidate in ranked if candidate.meta.title}
    if titles and not any(_matches_filename(title, stem) for title in titles):
        output_fn("")
        output_fn(
            f'  Fingerprint says this is "{ranked[0].meta.title}", which does not '
            "match the filename. Listen to the track before choosing — the file "
            "may be mislabeled."
        )

    top_stated = ranked[0].stated_duration
    if (file_duration is not None and top_stated is not None
            and abs(top_stated - file_duration) > DURATION_MISMATCH_LIMIT):
        output_fn("")
        output_fn(
            f"  This file runs {_mmss(file_duration)} but the matched recording "
            f"is {_mmss(top_stated)}. A fingerprint only covers the first two "
            "minutes, so a short edit or an extended version can match the wrong "
            "recording — check the track before choosing."
        )

    displayed: list[Candidate] = []
    for shown, hidden in groups:
        output_fn("")
        output_fn(f"  {_group_header(shown)}")
        album_width = max(len(c.meta.album) for c in shown) + 2
        for candidate in shown:
            displayed.append(candidate)
            output_fn(f"    {len(displayed)}. {_row(candidate, album_width)}")
        if hidden:
            output_fn(f"       + {hidden} more compilation(s), not shown")
    ranked = displayed

    if len(ranked) > 1:
        output_fn("")
        output_fn("Tip: option 1 is usually the right one.")

    while True:
        reply = input_fn("Type a number, press Enter for 1, or 's' to skip: ").strip().lower()
        if reply == "s":
            return None
        if reply == "":
            return ranked[0]
        if reply.isdigit() and 1 <= int(reply) <= len(ranked):
            return ranked[int(reply) - 1]
        output_fn("Enter a listed number, or 's' to skip.")
