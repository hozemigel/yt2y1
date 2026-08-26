# tests/test_artwork.py
from y1sync.models import TrackMeta
from y1sync.artwork import fetch_artwork, artwork_url_for


class FakeResponse:
    def __init__(self, content=b"", ok=True):
        self.content = content
        self.ok = ok


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return self.response


def test_returns_none_without_url(tmp_path):
    assert fetch_artwork(None, tmp_path) is None


def test_downloads_and_returns_bytes(tmp_path):
    session = FakeSession(FakeResponse(b"jpeg-bytes"))
    assert fetch_artwork("https://example.test/a.jpg", tmp_path, session) == b"jpeg-bytes"


def test_second_call_uses_cache(tmp_path):
    session = FakeSession(FakeResponse(b"jpeg-bytes"))
    url = "https://example.test/a.jpg"
    fetch_artwork(url, tmp_path, session)
    fetch_artwork(url, tmp_path, session)
    assert session.calls == 1


def test_returns_none_on_http_failure(tmp_path):
    session = FakeSession(FakeResponse(b"", ok=False))
    assert fetch_artwork("https://example.test/a.jpg", tmp_path, session) is None


def test_does_not_cache_a_failed_download(tmp_path):
    session = FakeSession(FakeResponse(b"", ok=False))
    fetch_artwork("https://example.test/a.jpg", tmp_path, session)
    assert list(tmp_path.glob("*.jpg")) == []


class FakeJsonSession:
    def __init__(self, payload, ok=True):
        self.payload = payload
        self.ok = ok
        self.params = None

    def get(self, url, params=None, timeout=None):
        self.params = params
        session = self

        class Response:
            ok = session.ok

            @staticmethod
            def json():
                return session.payload

        return Response()


def test_looks_up_artwork_for_a_fingerprinted_track():
    # AcoustID returns no cover art, so the album is looked up on iTunes.
    session = FakeJsonSession({"results": [
        {"artworkUrl100": "https://example.test/100x100bb.jpg"}
    ]})
    meta = TrackMeta(artist="Fleetwood Mac", title="Dreams", album="Rumours")
    assert artwork_url_for(meta, session).endswith("600x600bb.jpg")


def test_artwork_lookup_searches_by_artist_and_album():
    session = FakeJsonSession({"results": []})
    artwork_url_for(TrackMeta(artist="Black", title="X", album="Wonderful Life"), session)
    assert "Black" in session.params["term"]
    assert "Wonderful Life" in session.params["term"]


def test_artwork_lookup_returns_none_when_nothing_matches():
    session = FakeJsonSession({"results": []})
    meta = TrackMeta(artist="A", title="B", album="C")
    assert artwork_url_for(meta, session) is None


def test_artwork_lookup_returns_none_on_http_failure():
    session = FakeJsonSession({"results": []}, ok=False)
    meta = TrackMeta(artist="A", title="B", album="C")
    assert artwork_url_for(meta, session) is None


class FakeBadJsonSession:
    """A session whose response has a 200 status but an unparsable body."""

    def get(self, url, params=None, timeout=None):
        class Response:
            ok = True

            @staticmethod
            def json():
                raise ValueError("not valid json")

        return Response()


def test_artwork_lookup_returns_none_when_response_body_is_not_json():
    session = FakeBadJsonSession()
    meta = TrackMeta(artist="A", title="B", album="C")
    assert artwork_url_for(meta, session) is None


def test_artwork_lookup_returns_none_when_result_entry_is_not_a_dict():
    session = FakeJsonSession({"results": ["not-a-dict"]})
    meta = TrackMeta(artist="A", title="B", album="C")
    assert artwork_url_for(meta, session) is None
