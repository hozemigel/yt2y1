from pathlib import Path
import pytest
from y1sync.identify import (
    ACOUSTID_ENDPOINT, ITUNES_ENDPOINT, MUSICBRAINZ_ENDPOINT,
    AcoustIDKeyRejected, guess_query_from_filename, identify,
    parse_itunes_response, parse_acoustid_response,
)


def test_strips_youtube_suffixes():
    name = Path("Djo - End Of Beginning (Official Audio).mp3")
    assert guess_query_from_filename(name) == "Djo End Of Beginning"


def test_strips_bracketed_youtube_debris():
    name = Path("Goo Goo Dolls - Iris (Live in Buffalo) [Official Video].mp3")
    assert "Official Video" not in guess_query_from_filename(name)
    assert "Goo Goo Dolls" in guess_query_from_filename(name)


def test_strips_lyrics_marker():
    name = Path("Topic, Becky G - Sorry Papi (Lyrics).mp3")
    assert guess_query_from_filename(name) == "Topic, Becky G Sorry Papi"


def test_handles_filename_with_no_artist():
    assert guess_query_from_filename(Path("Fast Car.mp3")) == "Fast Car"


def test_parses_itunes_response_into_candidates():
    payload = {"results": [{
        "artistName": "The Cranberries",
        "trackName": "Ode to My Family",
        "collectionName": "No Need to Argue",
        "releaseDate": "1994-10-03T07:00:00Z",
        "primaryGenreName": "Rock",
        "trackNumber": 1,
        "artworkUrl100": "https://example.test/100x100bb.jpg",
    }]}
    cands = parse_itunes_response(payload)
    assert len(cands) == 1
    assert cands[0].meta.artist == "The Cranberries"
    assert cands[0].meta.year == "1994"
    assert cands[0].source == "itunes"
    # Artwork is upgraded from the thumbnail the API returns.
    assert cands[0].artwork_url.endswith("600x600bb.jpg")


def test_itunes_candidates_never_claim_fingerprint_confidence():
    payload = {"results": [{
        "artistName": "A", "trackName": "B", "collectionName": "C",
        "releaseDate": "2000-01-01T00:00:00Z", "primaryGenreName": "Pop",
        "trackNumber": 1, "artworkUrl100": "https://example.test/100x100bb.jpg",
    }]}
    assert parse_itunes_response(payload)[0].source == "itunes"


def test_keeps_a_cover_credit_that_merely_starts_with_a_noise_word():
    # "Audioslave" begins with "audio". Stripping it would query a cover
    # as though it were the original recording.
    name = Path("Radioactive (Audioslave Cover).mp3")
    assert "Audioslave" in guess_query_from_filename(name)


def test_still_strips_a_real_noise_marker():
    name = Path("Some Song (Official Audio).mp3")
    assert guess_query_from_filename(name) == "Some Song"


def test_parses_empty_itunes_response():
    assert parse_itunes_response({"results": []}) == []


def test_parses_acoustid_response_with_release_types():
    payload = {"results": [{"score": 0.98, "recordings": [{
        "title": "Dreams",
        "artists": [{"name": "Fleetwood Mac"}],
        "releasegroups": [
            {"title": "Rumours", "type": "Album",
             "secondarytypes": [], "releases": [
                 {"date": {"year": 1977, "month": 2, "day": 4}, "status": "Official"}]},
            {"title": "Greatest Hits", "type": "Album",
             "secondarytypes": ["Compilation"], "releases": [
                 {"date": {"year": 1988}, "status": "Official"}]},
        ],
    }]}]}
    cands = parse_acoustid_response(payload, score=0.98)
    albums = {c.meta.album for c in cands}
    assert albums == {"Rumours", "Greatest Hits"}
    compilation = next(c for c in cands if c.meta.album == "Greatest Hits")
    assert compilation.secondary_types == ("Compilation",)
    assert all(c.source == "acoustid" for c in cands)


def test_each_acoustid_result_keeps_its_own_score():
    # A weak second match must not inherit a strong first match's
    # confidence, or it could be auto-applied without review.
    def result(title, score):
        return {"score": score, "recordings": [{
            "title": title, "artists": [{"name": "A"}],
            "releasegroups": [{"title": title, "type": "Album",
                               "secondarytypes": [], "releases": [
                                   {"date": {"year": 1990}, "status": "Official"}]}],
        }]}

    payload = {"results": [result("Strong", 0.99), result("Weak", 0.42)]}
    by_title = {c.meta.title: c.confidence for c in parse_acoustid_response(payload)}
    assert by_title["Strong"] == 0.99
    assert by_title["Weak"] == 0.42


def test_acoustid_partial_dates_do_not_crash():
    payload = {"results": [{"score": 0.9, "recordings": [{
        "title": "T", "artists": [{"name": "A"}],
        "releasegroups": [{"title": "G", "type": "Album", "secondarytypes": [],
                           "releases": [{"date": {"year": 1990}, "status": "Official"}]}],
    }]}]}
    assert parse_acoustid_response(payload, score=0.9)[0].release_date == "1990-01-01"


# --- Routing regression tests ------------------------------------------
#
# These cover the half of the project's motivating failures that ranking
# cannot reach. Shaggy's "Angel" and Black's "Wonderful Life" were
# misidentified because the lookup guessed from the filename: one
# returned a 2020 re-recording in place of the 2000 original, the other a
# different artist entirely. Only a fingerprint distinguishes them,
# because the audio itself differs. Without these tests, deleting the
# AcoustID branch from identify() would keep the suite green.


class RoutingSession:
    """Records which endpoints were called and replays canned payloads."""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append(url)
        payload = self.payloads.get(url, {})
        session = self

        class Response:
            ok = True

            @staticmethod
            def json():
                return payload

        return Response()


# The real shape, confirmed against the live service: AcoustID names the
# recording and returns NO release data at all. An earlier fixture here
# invented a "releasegroups" key, which is why this suite passed while the
# tool silently fell through to filename guessing against the real API.
SHAGGY_ACOUSTID = {"results": [{"score": 0.97, "recordings": [{
    "id": "rec-shaggy-angel",
    "title": "Angel",
    "artists": [{"name": "Shaggy"}],
    "duration": 235.0,
}]}]}

# MusicBrainz supplies the releases, with the types ranking is built on.
SHAGGY_MUSICBRAINZ = {"releases": [{
    "title": "Hot Shot",
    "date": "2000-08-08",
    "status": "Official",
    "release-group": {"primary-type": "Album", "secondary-types": []},
}]}

SHAGGY_ITUNES = {"results": [{
    "artistName": "Shaggy",
    "trackName": "Angel (Hot Shot 2020) [feat. Sting]",
    "collectionName": "Hot Shot 2020 (Deluxe Edition)",
    "releaseDate": "2020-01-01T00:00:00Z",
    "primaryGenreName": "Reggae",
    "trackNumber": 6,
    "artworkUrl100": "https://example.test/100x100bb.jpg",
}]}


def test_fingerprint_route_beats_the_filename_guess(monkeypatch):
    # The real failure: a filename lookup returned the 2020 re-recording
    # with Sting; the file was the 2000 original with Rayvon.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (216, "AQADtEmkRSk"))
    session = RoutingSession({
        ACOUSTID_ENDPOINT: SHAGGY_ACOUSTID,
        f"{MUSICBRAINZ_ENDPOINT}/rec-shaggy-angel": SHAGGY_MUSICBRAINZ,
        ITUNES_ENDPOINT: SHAGGY_ITUNES,
    })

    found = identify(Path("Shaggy - Angel (Lyrics) Ft. Rayvon.mp3"),
                     api_key="key", session=session)

    assert [c.source for c in found] == ["acoustid"]
    assert found[0].meta.artist == "Shaggy"
    assert found[0].meta.album == "Hot Shot"
    assert found[0].meta.year == "2000"
    # The release types ranking needs must survive the MusicBrainz hop.
    assert found[0].release_group_type == "Album"
    assert found[0].release_status == "Official"
    # iTunes must never have been consulted once the fingerprint matched.
    assert ITUNES_ENDPOINT not in session.calls


def test_musicbrainz_is_consulted_for_release_data(monkeypatch):
    # AcoustID returns no releases, so skipping this hop would leave every
    # candidate without the type and date the ranking rules sort on --
    # making an original album indistinguishable from a compilation.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (216, "AQADtEmkRSk"))
    session = RoutingSession({
        ACOUSTID_ENDPOINT: SHAGGY_ACOUSTID,
        f"{MUSICBRAINZ_ENDPOINT}/rec-shaggy-angel": SHAGGY_MUSICBRAINZ,
        ITUNES_ENDPOINT: SHAGGY_ITUNES,
    })

    identify(Path("x.mp3"), api_key="key", session=session)

    assert f"{MUSICBRAINZ_ENDPOINT}/rec-shaggy-angel" in session.calls


def test_falls_back_when_musicbrainz_knows_no_releases(monkeypatch):
    # A recording with no releases yields no candidates, so the filename
    # route is still better than returning nothing.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (216, "AQADtEmkRSk"))
    session = RoutingSession({
        ACOUSTID_ENDPOINT: SHAGGY_ACOUSTID,
        f"{MUSICBRAINZ_ENDPOINT}/rec-shaggy-angel": {"releases": []},
        ITUNES_ENDPOINT: SHAGGY_ITUNES,
    })

    found = identify(Path("Shaggy - Angel.mp3"), api_key="key", session=session)

    assert [c.source for c in found] == ["itunes"]


def test_without_an_api_key_it_falls_back_to_the_filename(monkeypatch):
    # No key means no fingerprint route at all, so the candidate is a
    # filename guess and is marked as one for review.
    def explode(path):
        raise AssertionError("fingerprinting must not run without a key")

    monkeypatch.setattr("y1sync.identify.fingerprint", explode)
    session = RoutingSession({ITUNES_ENDPOINT: SHAGGY_ITUNES})

    found = identify(Path("Shaggy - Angel (Lyrics) Ft. Rayvon.mp3"), session=session)

    assert [c.source for c in found] == ["itunes"]
    assert session.calls == [ITUNES_ENDPOINT]


def test_falls_back_when_the_fingerprint_finds_nothing(monkeypatch):
    # chromaprint installed but the recording is unknown to AcoustID.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (216, "AQADtEmkRSk"))
    session = RoutingSession({ACOUSTID_ENDPOINT: {"results": []},
                              ITUNES_ENDPOINT: SHAGGY_ITUNES})

    found = identify(Path("Shaggy - Angel.mp3"), api_key="key", session=session)

    assert [c.source for c in found] == ["itunes"]
    assert session.calls == [ACOUSTID_ENDPOINT, ITUNES_ENDPOINT]


def test_falls_back_when_chromaprint_is_missing(monkeypatch):
    # fingerprint() returns None when fpcalc is not installed.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: None)
    session = RoutingSession({ITUNES_ENDPOINT: SHAGGY_ITUNES})

    found = identify(Path("Shaggy - Angel.mp3"), api_key="key", session=session)

    assert [c.source for c in found] == ["itunes"]
    assert session.calls == [ITUNES_ENDPOINT]


# --- Rejected key ------------------------------------------------------
#
# Found by running the tool against the real AcoustID service with a key
# of the wrong kind (a user key rather than an application key). The
# service answered {"error": {"code": 4, "message": "invalid API key"}}
# and identification silently fell through to guessing from the filename
# -- the exact failure this tool exists to prevent, made invisible.


class ErrorSession:
    def __init__(self, payload, status_ok=True):
        self.payload = payload
        self.status_ok = status_ok
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        session = self

        class Response:
            ok = session.status_ok

            @staticmethod
            def json():
                return session.payload

        return Response()


KEY_REJECTED = {"error": {"code": 4, "message": "invalid API key"}, "status": "error"}


def test_a_rejected_key_raises_instead_of_guessing(monkeypatch):
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (297, "AQADtEmSREoy"))
    session = ErrorSession(KEY_REJECTED, status_ok=False)

    with pytest.raises(AcoustIDKeyRejected):
        identify(Path("Black - Wonderful Life.mp3"), api_key="bad", session=session)

    # It must not have quietly asked iTunes instead.
    assert ITUNES_ENDPOINT not in session.calls


def test_a_rejected_key_is_caught_on_a_200_response_too(monkeypatch):
    # AcoustID reports some errors with a 200 and an error body.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (297, "AQADtEmSREoy"))
    session = ErrorSession(KEY_REJECTED, status_ok=True)

    with pytest.raises(AcoustIDKeyRejected):
        identify(Path("Black - Wonderful Life.mp3"), api_key="bad", session=session)


def test_the_message_names_the_fix(monkeypatch):
    # A user hitting this needs to know which kind of key to get.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (297, "AQADtEmSREoy"))
    session = ErrorSession(KEY_REJECTED, status_ok=False)
    try:
        identify(Path("x.mp3"), api_key="bad", session=session)
    except AcoustIDKeyRejected as exc:
        assert "new-application" in str(exc)
        assert "config.toml" in str(exc)
    else:
        raise AssertionError("expected AcoustIDKeyRejected")


def test_an_ordinary_http_failure_still_falls_back(monkeypatch):
    # A transient outage is not a bad key: fall through as before.
    monkeypatch.setattr("y1sync.identify.fingerprint", lambda p: (297, "AQADtEmSREoy"))
    session = ErrorSession({"error": {"code": 3, "message": "server busy"}}, status_ok=False)
    session.payloads = None

    found = identify(Path("Shaggy - Angel.mp3"), api_key="key", session=session)
    assert session.calls[-1] == ITUNES_ENDPOINT
    assert found == []
