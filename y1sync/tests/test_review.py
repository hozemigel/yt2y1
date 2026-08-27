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


def test_a_blank_line_precedes_a_new_recordings_group_header():
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
    # Group headers read "Artist — Title"; a row never contains that em dash.
    header_index = next(i for i, line in enumerate(lines) if "Save Tonight" in line and "—" in line)
    assert lines[header_index - 1] == ""


def test_a_single_recording_gets_exactly_one_group_header():
    lines = []
    options = [cand("Greatest Hits", secondary=("Compilation",)), cand("Rumours")]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "1",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    # A group header is exactly "  Artist — Title"; other lines (like the
    # mismatch warning here, since "X - Y" never matches "f.mp3") can
    # contain an em dash too without being one.
    headers = [line for line in lines if line == "  X — Y"]
    assert len(headers) == 1


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


def test_a_group_header_names_the_artist_and_title_once():
    # The artist and title used to repeat on every row -- the single
    # biggest source of clutter in a list that can run to a dozen rows.
    lines = []
    options = [cand("Rumours"), cand("Greatest Hits", secondary=("Compilation",))]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert "  X — Y" in lines
    # A row shows only what varies between releases -- not the repeated
    # artist/title.
    assert not any(line.strip().startswith("1.") and "X" in line for line in lines)


def test_a_rows_year_and_type_are_shown_but_not_the_repeated_title():
    lines = []
    meta = TrackMeta(artist="Black", title="Wonderful Life", album="At Wembley Arena", year="1987")
    single = Candidate(meta=meta, confidence=0.95, source="acoustid",
                       release_group_type="Album", secondary_types=("Live",),
                       release_status="Official", release_date="1987-01-01")
    choose_candidate(Path("f.mp3"), [single], input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    row = next(line for line in lines if line.strip().startswith("1."))
    assert "1987" in row
    assert "live" in row.lower()
    assert "Wonderful Life" not in row  # only in the group header, above


def test_the_header_says_one_match_for_a_single_candidate():
    lines = []
    choose_candidate(Path("f.mp3"), [cand("Rumours")], input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert any("One match found for:" in line for line in lines)
    assert not any("Multiple matches for:" in line for line in lines)


def test_the_header_says_multiple_for_more_than_one_candidate():
    lines = []
    options = [cand("Rumours"), cand("Greatest Hits", secondary=("Compilation",))]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert any("Multiple matches for:" in line for line in lines)
    assert not any("One match found for:" in line for line in lines)


def test_a_tip_is_shown_only_when_there_is_more_than_one_option():
    lines = []
    choose_candidate(Path("f.mp3"), [cand("Rumours")], input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert not any("usually the right one" in line for line in lines)

    lines = []
    options = [cand("Rumours"), cand("Greatest Hits", secondary=("Compilation",))]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert any("usually the right one" in line for line in lines)
