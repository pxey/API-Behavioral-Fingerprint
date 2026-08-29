from abf.recorder import Recorder, normalize_path
from abf.storage import InMemoryStorage


def test_normalize_path_collapses_numeric_ids():
    assert normalize_path("/users/123") == "/users/{id}"
    assert normalize_path("/users/123/orders/456") == "/users/{id}/orders/{id}"


def test_normalize_path_collapses_uuids():
    assert normalize_path("/sessions/550e8400-e29b-41d4-a716-446655440000") == "/sessions/{id}"


def test_normalize_path_keeps_static_segments():
    assert normalize_path("/users/me/profile") == "/users/me/profile"


def test_record_raw_extracts_endpoint_and_fields():
    recorder = Recorder(InMemoryStorage())
    obs = recorder.record_raw(
        "get", "/users/123", 200, latency_ms=15.0, json_body={"id": 123, "name": "Ada", "meta": {"active": True}}
    )
    assert obs.endpoint == "GET /users/{id}"
    assert obs.body_fields["id"] == "int"
    assert obs.body_fields["name"] == "string"
    assert obs.body_fields["meta.active"] == "bool"
    assert not obs.is_error


def test_record_raw_flags_error_status():
    recorder = Recorder(InMemoryStorage())
    obs = recorder.record_raw("GET", "/users/1", 500, latency_ms=5.0)
    assert obs.is_error


def test_record_raw_detects_pagination_keys():
    recorder = Recorder(InMemoryStorage())
    obs = recorder.record_raw(
        "GET", "/users", 200, latency_ms=10.0, json_body={"items": [], "next_cursor": "abc"}
    )
    assert "next_cursor" in obs.pagination_keys
