"""Ask the user to resolve an ambiguous identification."""

from collections.abc import Sequence
from pathlib import Path

from .models import Candidate
from .ranking import rank_candidates


def _describe(candidate: Candidate) -> str:
    parts = [f"{candidate.meta.artist} - {candidate.meta.title}"]
    parts.append(f"[{candidate.meta.album}]")
    if candidate.meta.year:
        parts.append(f"({candidate.meta.year})")
    if candidate.secondary_types:
        parts.append(f"<{', '.join(candidate.secondary_types)}>")
    return " ".join(parts)


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
    for index, candidate in enumerate(ranked, start=1):
        output_fn(f"  {index}. {_describe(candidate)}")

    while True:
        reply = input_fn("Choose [1] or 's' to skip: ").strip().lower()
        if reply == "s":
            return None
        if reply == "":
            return ranked[0]
        if reply.isdigit() and 1 <= int(reply) <= len(ranked):
            return ranked[int(reply) - 1]
        output_fn("Enter a listed number, or 's' to skip.")
