from abf.compare import compare_fingerprints
from abf.models import DriftCategory, DriftKind
from abf.recorder import Recorder
from abf.storage import InMemoryStorage


def _fp(storage, recs, endpoint="GET /users/{id}"):
    from abf.models import EndpointFingerprint

    obs = storage.observations_for(endpoint)
    return EndpointFingerprint.from_observations(endpoint, obs)


def test_schema_unchanged_but_behavior_drifts():
    """The exact motivating example from the spec: schema stays the same,
    but the endpoint starts returning 429s and gets slower."""
    storage = InMemoryStorage()
    recorder = Recorder(storage)

    for i in range(10):
        recorder.record_raw("GET", f"/users/{i}", 200, latency_ms=20.0, json_body={"id": i, "name": "x"})
    baseline = _fp(storage, None)

    storage2 = InMemoryStorage()
    recorder2 = Recorder(storage2)
    for i in range(7):
        recorder2.record_raw("GET", f"/users/{i}", 200, latency_ms=80.0, json_body={"id": i, "name": "x"})
    for i in range(3):
        recorder2.record_raw("GET", f"/users/{i}", 429, latency_ms=5.0)
    current = _fp(storage2, None)

    drifts = compare_fingerprints(baseline, current)
    kinds = {d.kind for d in drifts}
    categories = {d.kind: d.category for d in drifts}

    assert DriftKind.NEW_ERROR_STATUS in kinds
    assert DriftKind.LATENCY_CHANGED in kinds
    assert categories[DriftKind.NEW_ERROR_STATUS] == DriftCategory.BEHAVIOR
    assert categories[DriftKind.LATENCY_CHANGED] == DriftCategory.BEHAVIOR
    # no field-shape drift kinds should appear — schema truly unchanged
    schema_kinds = {DriftKind.FIELD_ADDED, DriftKind.FIELD_REMOVED, DriftKind.FIELD_TYPE_CHANGED}
    assert not (kinds & schema_kinds)


def test_field_added_is_schema_drift():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    for i in range(5):
        recorder.record_raw("GET", f"/users/{i}", 200, latency_ms=10.0, json_body={"id": i})
    baseline = _fp(storage, None)

    storage2 = InMemoryStorage()
    recorder2 = Recorder(storage2)
    for i in range(5):
        recorder2.record_raw("GET", f"/users/{i}", 200, latency_ms=10.0, json_body={"id": i, "email": "a@b.com"})
    current = _fp(storage2, None)

    drifts = compare_fingerprints(baseline, current)
    added = [d for d in drifts if d.kind == DriftKind.FIELD_ADDED]
    assert len(added) == 1
    assert added[0].field == "email"
    assert added[0].category == DriftCategory.SCHEMA


def test_field_type_changed_is_schema_drift():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    for _ in range(5):
        recorder.record_raw("GET", "/x", 200, latency_ms=10.0, json_body={"count": 3})
    baseline = _fp(storage, None, endpoint="GET /x")

    storage2 = InMemoryStorage()
    recorder2 = Recorder(storage2)
    for _ in range(5):
        recorder2.record_raw("GET", "/x", 200, latency_ms=10.0, json_body={"count": "3"})
    current = _fp(storage2, None, endpoint="GET /x")

    drifts = compare_fingerprints(baseline, current)
    type_changes = [d for d in drifts if d.kind == DriftKind.FIELD_TYPE_CHANGED]
    assert len(type_changes) == 1
    assert type_changes[0].field == "count"


def test_no_drift_for_identical_fingerprints():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    for i in range(5):
        recorder.record_raw("GET", f"/users/{i}", 200, latency_ms=10.0, json_body={"id": i})
    fp = _fp(storage, None)

    assert compare_fingerprints(fp, fp) == []
