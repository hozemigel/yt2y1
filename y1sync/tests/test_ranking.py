from y1sync.models import TrackMeta, Candidate
from y1sync.ranking import rank_candidates, decide


def cand(album, conf=0.95, primary="Album", secondary=(),
         status="Official", date="2000-01-01", source="acoustid"):
    return Candidate(
        meta=TrackMeta(artist="X", title="Y", album=album),
        confidence=conf, source=source, release_group_type=primary,
        secondary_types=secondary, release_status=status, release_date=date,
    )


def test_prefers_album_over_compilation():
    # The real Fleetwood Mac case: Rumours, not Greatest Hits.
    # Note: both candidates default to primary="Album" here, so this actually
    # exercises level 2 (deprioritised secondary types), not level 1.
    ranked = rank_candidates([
        cand("Greatest Hits", secondary=("Compilation",), date="1988-01-01"),
        cand("Rumours", date="1977-02-04"),
    ])
    assert ranked[0].meta.album == "Rumours"


def test_prefers_original_over_later_compilation():
    # The real Cranberries case: No Need To Argue, not Stars.
    # Note: both candidates default to primary="Album" here, so this actually
    # exercises level 2 (deprioritised secondary types), not level 1.
    ranked = rank_candidates([
        cand("Stars: The Best of", secondary=("Compilation",), date="2002-09-02"),
        cand("No Need To Argue", date="1994-10-03"),
    ])
    assert ranked[0].meta.album == "No Need To Argue"


def test_prefers_album_primary_type_over_compilation_primary_type():
    # Isolates level 1: release-group primary type "Album" vs "Compilation",
    # with no secondary types involved, otherwise equal.
    ranked = rank_candidates([
        cand("Various Artists Set", primary="Compilation"),
        cand("The Album", primary="Album"),
    ])
    assert ranked[0].meta.album == "The Album"


def test_prefers_earliest_release_among_equals():
    # The real Shaggy case: Hot Shot (2000), not the 2020 re-recording.
    ranked = rank_candidates([
        cand("Hot Shot 2020", date="2020-01-01"),
        cand("Hot Shot", date="2000-08-08"),
    ])
    assert ranked[0].meta.album == "Hot Shot"


def test_deprioritises_live_and_remix():
    ranked = rank_candidates([
        cand("Live In Buffalo", secondary=("Live",), date="1998-01-01"),
        cand("Dizzy Up the Girl", date="1998-09-22"),
    ])
    assert ranked[0].meta.album == "Dizzy Up the Girl"


def test_prefers_official_over_bootleg():
    ranked = rank_candidates([
        cand("Bootleg", status="Bootleg", date="1970-01-01"),
        cand("Official Album", status="Official", date="1999-01-01"),
    ])
    assert ranked[0].meta.album == "Official Album"


def test_handles_missing_dates_without_crashing():
    ranked = rank_candidates([cand("No Date", date=None), cand("Dated", date="1990-01-01")])
    assert len(ranked) == 2


def test_single_confident_candidate_applies_automatically():
    pick, needs_review = decide([cand("Rumours", conf=0.95)])
    assert needs_review is False
    assert pick.meta.album == "Rumours"


def test_multiple_releases_always_ask():
    # High confidence in the recording says nothing about which release.
    pick, needs_review = decide([cand("Rumours", conf=0.99), cand("Greatest Hits", conf=0.99)])
    assert needs_review is True
    assert pick.meta.album == "Rumours"


def test_low_confidence_asks_even_when_unique():
    pick, needs_review = decide([cand("Maybe", conf=0.5)])
    assert needs_review is True


def test_filename_sourced_candidates_always_ask():
    # This is the 27% failure rate that motivated the project.
    pick, needs_review = decide([cand("Guess", conf=1.0, source="itunes")])
    assert needs_review is True


def test_no_candidates_needs_review_with_no_pick():
    pick, needs_review = decide([])
    assert pick is None
    assert needs_review is True


def test_collapses_the_same_album_in_many_pressings():
    # MusicBrainz models each pressing as its own release, so a single
    # album can arrive a dozen times. Found against the live service: one
    # track offered 31 candidates, most of them indistinguishable.
    pressings = [cand("Wonderful Life", date="1987-01-01") for _ in range(10)]
    ranked = rank_candidates(pressings)
    assert len(ranked) == 1


def test_keeps_genuinely_different_albums():
    ranked = rank_candidates([
        cand("Rumours", date="1977-02-04"),
        cand("Greatest Hits", secondary=("Compilation",), date="1988-01-01"),
    ])
    assert len(ranked) == 2


def test_dedupe_keeps_the_best_ranked_of_a_duplicate_set():
    # The compilation and the album share a title here, so only the
    # better-ranked one may survive.
    ranked = rank_candidates([
        cand("Hot Shot", secondary=("Compilation",), date="2000-08-08"),
        cand("Hot Shot", date="2000-08-08"),
    ])
    assert len(ranked) == 1
    assert ranked[0].secondary_types == ()


def test_dedupe_ignores_case_differences():
    ranked = rank_candidates([cand("Wonderful Life"), cand("WONDERFUL LIFE")])
    assert len(ranked) == 1


def test_an_original_single_beats_a_compilation_album():
    # Found on a real track: "Be Mine" was released as a single, and
    # ranking put the compilation "Bravo Hits 130" first because a
    # compilation is still typed as an Album. Nothing derivative belongs
    # at the top, whatever its primary type claims.
    ranked = rank_candidates([
        cand("Bravo Hits 130", primary="Album",
             secondary=("Compilation",), date="2025-07-25"),
        cand("Be Mine", primary="Single", date="2025-05-16"),
    ])
    assert ranked[0].meta.album == "Be Mine"


def test_an_album_still_beats_a_single_when_neither_is_derivative():
    # The Album preference is not discarded, only subordinated.
    ranked = rank_candidates([
        cand("Some Single", primary="Single", date="1990-01-01"),
        cand("Some Album", primary="Album", date="1990-01-01"),
    ])
    assert ranked[0].meta.album == "Some Album"


def _recording(title, album, conf, **kwargs):
    kwargs.setdefault("primary", "Album")
    kwargs.setdefault("date", "2000-01-01")
    candidate = cand(album, conf=conf, **kwargs)
    return Candidate(
        meta=TrackMeta(artist=candidate.meta.artist, title=title, album=album),
        confidence=candidate.confidence, source=candidate.source,
        release_group_type=candidate.release_group_type,
        secondary_types=candidate.secondary_types,
        release_status=candidate.release_status,
        release_date=candidate.release_date,
    )


def test_a_different_recordings_releases_stay_together():
    # Found on a real track: AcoustID named two different recordings at
    # near-equal confidence (see identify's near-tied-results test). Pooling
    # every release by quality alone scattered the correct recording's one
    # compilation between the wrong recording's several official albums,
    # with nothing marking that they were even different songs.
    releases = [
        _recording("Are You Still Having Fun?", "Living in the Present Future",
                   conf=0.9767, date="2000-01-01"),
        _recording("Are You Still Having Fun?", "Most Wanted Summer 2000",
                   conf=0.9767, secondary=("Compilation",), date="2000-06-01"),
        _recording("Save Tonight", "Promo Only: Modern Rock Radio, July 1998",
                   conf=0.9747, secondary=("Compilation",), date="1998-07-01"),
    ]
    ranked = rank_candidates(releases)
    titles = [c.meta.title for c in ranked]
    assert titles == [
        "Are You Still Having Fun?", "Are You Still Having Fun?", "Save Tonight",
    ]


def test_groups_are_ordered_by_the_recordings_own_confidence():
    # The lower-confidence recording's compilation must not leapfrog into
    # the higher-confidence recording's block just because compilations
    # sort low within a block.
    releases = [
        _recording("Weaker Match", "Weaker's Only Release", conf=0.80,
                    secondary=("Compilation",), date="1998-01-01"),
        _recording("Stronger Match", "Stronger's Only Release", conf=0.95,
                    secondary=("Compilation",), date="1998-01-01"),
    ]
    ranked = rank_candidates(releases)
    assert ranked[0].meta.title == "Stronger Match"


def test_dedupe_merges_curly_and_straight_apostrophes():
    # Found on a real track: MusicBrainz catalogued "It Ain't Me" twice,
    # differing only in apostrophe style, and both survived deduping as
    # if they were different releases.
    ranked = rank_candidates([
        cand("It Ain’t Me", date="2017-02-17"),
        cand("It Ain't Me", date="2017-02-17"),
    ])
    assert len(ranked) == 1


def test_dedupe_merges_curly_and_straight_quotes_and_dashes():
    ranked = rank_candidates([
        cand("“Greatest” Hits – Vol. 1", date="2000-01-01"),
        cand('"Greatest" Hits - Vol. 1', date="2000-01-01"),
    ])
    assert len(ranked) == 1


def test_lone_compilation_candidate_needs_review():
    # A lone candidate with Compilation secondary type must surface for review.
    # Being the only candidate is not proof of an unambiguous match — it is
    # usually just thin MusicBrainz coverage, and the one release catalogued
    # is often a compilation rather than the original album.
    pick, needs_review = decide([cand("Rock Times Vol. 9", secondary=("Compilation",), conf=0.95)])
    assert needs_review is True
    assert pick is not None


def test_lone_live_candidate_needs_review():
    # Live releases are derivative; a lone live match is not auto-applicable.
    pick, needs_review = decide([cand("Live in Berlin", secondary=("Live",), conf=0.98)])
    assert needs_review is True
    assert pick is not None


def test_lone_remix_candidate_needs_review():
    # Remix releases are derivative; a lone remix match is not auto-applicable.
    pick, needs_review = decide([cand("Remixed", secondary=("Remix",), conf=0.97)])
    assert needs_review is True
    assert pick is not None
