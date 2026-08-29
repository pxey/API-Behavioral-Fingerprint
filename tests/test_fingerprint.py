from abf.models import EndpointFingerprint
from abf.recorder import Recorder
from abf.storage import InMemoryStorage


def test_fingerprint_aggregates_status_and_fields():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    for i in range(5):
        recorder.record_raw("GET", f"/users/{i}", 200, latency_ms=10.0 + i, json_body={"id": i, "name": "x"})
    recorder.record_raw("GET", "/users/9", 404, latency_ms=5.0)

    obs = storage.observations_for("GET /users/{id}")
    fp = EndpointFingerprint.from_observations("GET /users/{id}", obs)

    assert fp.sample_count == 6
    assert fp.status_codes[200] == 5
    assert fp.status_codes[404] == 1
    assert "id" in fp.fields
    assert fp.fields["id"].present_rate(fp.sample_count) == 5 / 6


def test_fingerprint_latency_percentiles():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    for latency in [10, 20, 30, 40, 100]:
        recorder.record_raw("GET", "/ping", 200, latency_ms=float(latency))

    obs = storage.observations_for("GET /ping")
    fp = EndpointFingerprint.from_observations("GET /ping", obs)
    assert fp.latency_p50 == 30
    assert fp.latency_p99 == 100


def test_fingerprint_error_rate():
    storage = InMemoryStorage()
    recorder = Recorder(storage)
    recorder.record_raw("GET", "/x", 200, latency_ms=1.0)
    recorder.record_raw("GET", "/x", 500, latency_ms=1.0)

    obs = storage.observations_for("GET /x")
    fp = EndpointFingerprint.from_observations("GET /x", obs)
    assert fp.error_rate == 0.5
