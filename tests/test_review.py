from pathlib import Path
from y1sync.models import TrackMeta, Candidate
from y1sync.review import choose_candidate


def cand(album, date="2000-01-01", secondary=()):
    return Candidate(
        meta=TrackMeta(artist="X", title="Y", album=album),
        confidence=0.95, source="acoustid", release_group_type="Album",
        secondary_types=secondary, release_status="Official", release_date=date,
    )


def test_selecting_a_number_returns_that_candidate():
    options = [cand("Rumours"), cand("Greatest Hits")]
    chosen = choose_candidate(Path("f.mp3"), options,
                              input_fn=lambda _: "2", output_fn=lambda *a: None)
    assert chosen.meta.album == "Greatest Hits"


def test_empty_input_accepts_the_top_ranked_option():
    options = [cand("Greatest Hits", secondary=("Compilation",)), cand("Rumours")]
    chosen = choose_candidate(Path("f.mp3"), options,
                              input_fn=lambda _: "", output_fn=lambda *a: None)
    assert chosen.meta.album == "Rumours"


def test_skip_returns_none():
    chosen = choose_candidate(Path("f.mp3"), [cand("A")],
                              input_fn=lambda _: "s", output_fn=lambda *a: None)
    assert chosen is None


def test_invalid_input_reprompts():
    replies = iter(["banana", "99", "1"])
    chosen = choose_candidate(Path("f.mp3"), [cand("Rumours")],
                              input_fn=lambda _: next(replies),
                              output_fn=lambda *a: None)
    assert chosen.meta.album == "Rumours"


def test_no_candidates_returns_none_without_prompting():
    def explode(_):
        raise AssertionError("must not prompt when there is nothing to choose")

    assert choose_candidate(Path("f.mp3"), [], input_fn=explode,
                            output_fn=lambda *a: None) is None


def test_options_are_displayed_best_first():
    lines = []
    options = [cand("Greatest Hits", secondary=("Compilation",)), cand("Rumours")]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "1",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    shown = "\n".join(lines)
    assert shown.index("Rumours") < shown.index("Greatest Hits")
