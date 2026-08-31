from pathlib import Path
from y1sync.models import TrackMeta, Candidate
from y1sync.review import choose_candidate


def cand(album, date="2000-01-01", secondary=(), stated_duration=None):
    return Candidate(
        meta=TrackMeta(artist="X", title="Y", album=album),
        confidence=0.95, source="acoustid", release_group_type="Album",
        secondary_types=secondary, release_status="Official", release_date=date,
        stated_duration=stated_duration,
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


def test_a_length_gap_is_called_out_with_both_times():
    lines = []
    options = [cand("Original Album", stated_duration=245.0)]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)),
                     file_duration=88.0)
    shown = "\n".join(lines)
    assert "1:28" in shown and "4:05" in shown
    assert "first two minutes" in shown


def test_no_length_warning_when_the_lengths_agree():
    lines = []
    options = [cand("Original Album", stated_duration=182.0)]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)),
                     file_duration=180.0)
    assert not any("first two minutes" in line for line in lines)


def test_no_length_warning_without_a_file_duration():
    lines = []
    options = [cand("Original Album", stated_duration=245.0)]
    choose_candidate(Path("f.mp3"), options, input_fn=lambda _: "s",
                     output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)))
    assert not any("first two minutes" in line for line in lines)


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


def test_a_youtube_sourced_top_option_is_labelled_from_the_youtube_page():
    lines = []
    cand = Candidate(
        meta=TrackMeta(artist="SZA", title="Snooze", album="SOS", year="2022"),
        confidence=0.0, source="youtube", release_group_type="Album",
        release_status="Official", release_date=None,
    )
    choose_candidate(Path("snooze.mp3"), [cand],
                     input_fn=lambda _: "", output_fn=lines.append)
    assert any(
        "From the YouTube page: SZA — Snooze (SOS, 2022)" in line
        for line in lines
    )


def test_no_youtube_line_for_a_fingerprint_match():
    lines = []
    choose_candidate(Path("f.mp3"), [cand("Rumours")],
                     input_fn=lambda _: "", output_fn=lines.append)
    assert not any("From the YouTube page" in line for line in lines)


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


def _youtube_cand(artist="SZA", title="Snooze", album="SOS", year="2022"):
    return Candidate(
        meta=TrackMeta(artist=artist, title=title, album=album, year=year),
        confidence=0.1, source="youtube", release_group_type="Album",
        release_status="Official", release_date=None,
    )


def test_the_youtube_line_shows_even_when_that_candidate_is_not_first():
    # What the YouTube page claimed is context for the whole list, not a
    # property of whatever happens to rank first.
    lines = []
    choose_candidate(Path("snooze.mp3"), [cand("Rumours"), _youtube_cand()],
                     input_fn=lambda _: "s", output_fn=lines.append)
    assert any(
        "From the YouTube page: SZA — Snooze (SOS, 2022)" in line for line in lines
    )


def test_a_filename_mismatch_on_a_fingerprint_match_says_so():
    lines = []
    choose_candidate(Path("something else entirely.mp3"), [cand("Rumours")],
                     input_fn=lambda _: "s", output_fn=lines.append)
    assert any('Fingerprint says this is "Y"' in line for line in lines)


def test_a_filename_mismatch_without_a_fingerprint_does_not_claim_one():
    # Nothing fingerprinted this file, so the warning must not borrow the
    # fingerprint's authority for what is only a guess from the page.
    lines = []
    choose_candidate(Path("something else entirely.mp3"), [_youtube_cand()],
                     input_fn=lambda _: "s", output_fn=lines.append)
    warning = [line for line in lines if "does not match the filename" in line]
    assert warning
    assert "Fingerprint" not in "\n".join(lines)


def _amy(title, album, conf, date):
    return Candidate(
        meta=TrackMeta(artist="Amy Macdonald", title=title, album=album),
        confidence=conf, source="acoustid", release_group_type="Album",
        release_status="Official", release_date=date,
    )


def test_the_filename_breaks_a_near_tie_between_two_different_songs():
    # Found on a real track: AcoustID split a near-tie across two
    # recordings, and ranking put the marginally-higher-scored wrong song
    # first -- so Enter, and the "option 1" tip, pointed at a song the
    # file's own name says it is not.
    options = [
        _amy("Don’t Tell Me That It’s Over", "Don’t Tell Me That It’s Over",
             0.9767, "2010-03-08"),
        _amy("Slow It Down", "Slow It Down", 0.9747, "2022-05-06"),
    ]
    chosen = choose_candidate(
        Path("Amy Macdonald - Slow It Down (Official Audio).mp3"), options,
        input_fn=lambda _: "", output_fn=lambda *a: None,
    )
    assert chosen.meta.title == "Slow It Down"


def test_the_filename_matching_song_is_listed_and_numbered_first():
    options = [
        _amy("Don’t Tell Me That It’s Over", "Don’t Tell Me That It’s Over",
             0.9767, "2010-03-08"),
        _amy("Slow It Down", "Slow It Down", 0.9747, "2022-05-06"),
    ]
    lines = []
    first = choose_candidate(
        Path("Amy Macdonald - Slow It Down (Official Audio).mp3"), options,
        input_fn=lambda _: "1",
        output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)),
    )
    assert first.meta.title == "Slow It Down"
    shown = "\n".join(lines)
    assert shown.index("Slow It Down") < shown.index("Don’t Tell Me That It’s Over")


def test_a_near_tie_is_left_alone_when_the_top_song_already_matches():
    # The promotion must not fire when ranking already has it right.
    options = [
        _amy("Slow It Down", "Slow It Down", 0.9767, "2022-05-06"),
        _amy("Don’t Tell Me That It’s Over", "Don’t Tell Me That It’s Over",
             0.9747, "2010-03-08"),
    ]
    chosen = choose_candidate(
        Path("Amy Macdonald - Slow It Down (Official Audio).mp3"), options,
        input_fn=lambda _: "", output_fn=lambda *a: None,
    )
    assert chosen.meta.title == "Slow It Down"


def test_no_promotion_when_two_different_songs_both_match_the_filename():
    # Ambiguous evidence -- leave ranking's order and let the user pick.
    options = [
        _amy("Slow It Down (Radio Edit)", "Single", 0.9767, "2010-01-01"),
        _amy("Slow It Down", "A Curious Thing", 0.9747, "2010-03-08"),
    ]
    lines = []
    choose_candidate(
        Path("Amy Macdonald - Slow It Down.mp3"), options,
        input_fn=lambda _: "s",
        output_fn=lambda *a: lines.append(" ".join(str(x) for x in a)),
    )
    shown = "\n".join(lines)
    assert shown.index("Slow It Down (Radio Edit)") < shown.index("A Curious Thing")
