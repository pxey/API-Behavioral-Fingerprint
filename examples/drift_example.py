"""Example: simulate a day of "before" traffic and a day of "after"
traffic where the API silently started rate-limiting and a field went
from required to optional, then detect and explain the drift.

Run:
    python examples/drift_example.py
"""

from __future__ import annotations

from abf import EndpointFingerprint, Recorder, compare_fingerprints
from abf.storage import InMemoryStorage


def record_before(recorder: Recorder) -> None:
    for i in range(20):
        recorder.record_raw(
            "GET", f"/orders/{i}", 200, latency_ms=30.0, json_body={"id": i, "total": 42.5, "coupon": "SAVE10"}
        )


def record_after(recorder: Recorder) -> None:
    for i in range(15):
        recorder.record_raw("GET", f"/orders/{i}", 200, latency_ms=35.0, json_body={"id": i, "total": 42.5})
    for i in range(15, 20):
        recorder.record_raw("GET", f"/orders/{i}", 429, latency_ms=2.0)


def main() -> None:
    before_storage = InMemoryStorage()
    record_before(Recorder(before_storage))
    baseline = EndpointFingerprint.from_observations(
        "GET /orders/{id}", before_storage.observations_for("GET /orders/{id}")
    )

    after_storage = InMemoryStorage()
    record_after(Recorder(after_storage))
    current = EndpointFingerprint.from_observations(
        "GET /orders/{id}", after_storage.observations_for("GET /orders/{id}")
    )

    print("== Drift report for GET /orders/{id} ==")
    for drift in compare_fingerprints(baseline, current):
        print(drift.explain())


if __name__ == "__main__":
    main()
