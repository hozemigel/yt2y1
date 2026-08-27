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


def _recording(title, album, conf=0.95):
    return Candidate(
        meta=TrackMeta(artist="Eagle-Eye Cherry", title=title, album=album),
        confidence=conf, source="acoustid", release_group_type="Album",
        secondary_types=(), release_status="Official", release_date="2000-01-01",
    )


def test_a_blank_line_separates_different_recordings():
    # Found on a real track: a near-tied AcoustID match named two songs.
    # Pooled together with no marker, the true match read as one stray
    # entry among the wrong song's many releases instead of a second song.
    lines = []
    options = [
        _recording("Are You Still Having Fun?", "Living in the Present Future", conf=0.9767),
        _recording("Are You Still Having Fun?", "Most Wanted Summer 2000", conf=0.9767),
        _recording("Save Tonight", "Promo Only: Modern Rock Radio, July 1998", conf=0.9747),
    ]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    # One blank line, right before the "Save Tonight" entry.
    blank_indices = [i for i, line in enumerate(lines) if line == ""]
    save_tonight_index = next(i for i, line in enumerate(lines) if "Save Tonight" in line)
    assert blank_indices == [save_tonight_index - 1]


def test_no_blank_line_when_every_option_is_the_same_recording():
    lines = []
    options = [cand("Greatest Hits", secondary=("Compilation",)), cand("Rumours")]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "1",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert "" not in lines


def _kygo(title, album, secondary=(), conf=0.97):
    return Candidate(
        meta=TrackMeta(artist="Kygo", title=title, album=album),
        confidence=conf, source="acoustid", release_group_type="Album",
        secondary_types=secondary, release_status="Official", release_date="2017-01-01",
    )


def _compilation(n):
    return _kygo("It Ain't Me", f"Compilation {n}", secondary=("Compilation",))


def test_a_long_run_of_compilations_is_collapsed_to_a_note():
    # Found on a real track: 17 compilations for one song buried a second,
    # unrelated song further down the list.
    lines = []
    options = [_kygo("It Ain't Me", "It Ain't Me")] + [_compilation(n) for n in range(17)]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))

    numbered = [l for l in lines if l.strip()[:1].isdigit()]
    # The original, plus MAX_DERIVATIVE_SHOWN compilations -- not all 17.
    assert len(numbered) == 3
    assert any("15 more compilation" in l for l in lines)


def test_a_capped_groups_numbering_still_selects_correctly():
    # The group after a capped one must not have its numbers thrown off
    # by compilations that were counted but never printed.
    options = (
        [_kygo("It Ain't Me", "It Ain't Me")]
        + [_compilation(n) for n in range(17)]
        + [_kygo("Stranger Things", "Kids in Love", conf=0.965)]
    )
    chosen = choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "4",
                              output_fn=lambda *a: None)
    assert chosen.meta.title == "Stranger Things"


def test_a_short_run_of_compilations_is_not_collapsed():
    options = [_kygo("It Ain't Me", "It Ain't Me")] + [_compilation(n) for n in range(2)]
    lines = []
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert not any("more compilation" in l for l in lines)
