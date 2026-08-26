import dataclasses
import pytest
from y1sync.models import TrackMeta, Candidate


def test_trackmeta_requires_core_fields():
    meta = TrackMeta(artist="Fleetwood Mac", title="Dreams", album="Rumours")
    assert meta.artist == "Fleetwood Mac"
    assert meta.year is None


def test_trackmeta_is_frozen():
    meta = TrackMeta(artist="A", title="B", album="C")
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.artist = "changed"


def test_candidate_defaults_are_empty_not_none():
    meta = TrackMeta(artist="A", title="B", album="C")
    cand = Candidate(meta=meta, confidence=0.95, source="acoustid")
    assert cand.secondary_types == ()
    assert cand.release_status is None
