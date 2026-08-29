# API Behavioral Fingerprint

Detects **undocumented behavioral changes** in APIs by observing real
request/response traffic — not by diffing an OpenAPI schema.

```
Request -> Response -> Behavioral Observation -> Fingerprint
        -> Historical Comparison -> Drift Detection
```

## Why

Schema validators catch it when a field is renamed or removed. They miss
everything else:

- The endpoint starts returning `429` under a schema that never changed.
- p95 latency triples.
- A field becomes conditionally absent instead of always present.
- Pagination silently switches from offset-based to cursor-based.
- The error response format changes shape.

This project fingerprints *behavior*, not just schema, and explicitly
labels every finding as **schema drift** (the data shape changed) or
**behavior drift** (how the endpoint behaves changed) so you know which
kind of regression you're looking at.

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.12+. The only hard runtime dependency is `pydantic`.
The proxy mode is stdlib-only (no dependency required to run it); the
optional `sdk` extra (`httpx`) is only for the convenience wrapper.

## Quick start

```python
from abf import Recorder, EndpointFingerprint, compare_fingerprints
from abf.storage import SQLiteStorage

storage = SQLiteStorage("abf.db")
recorder = Recorder(storage)

# Record traffic (from your own HTTP client, the proxy, or tests)
recorder.record_raw("GET", "/users/123", 200, latency_ms=42.0,
                     json_body={"id": 123, "name": "Ada"})

# Later: build a fingerprint and compare against a saved baseline
obs = storage.observations_for("GET /users/{id}")
current = EndpointFingerprint.from_observations("GET /users/{id}", obs)

drifts = compare_fingerprints(baseline_fingerprint, current)
for d in drifts:
    print(d.explain())
```

Paths are automatically normalized — `/users/123` and `/users/456` both
fingerprint as `GET /users/{id}`.

### What each drift record tells you

Every `DriftRecord` answers exactly the questions you need to triage it:

```python
drift.category      # "schema_drift" or "behavior_drift"
drift.kind          # e.g. "new_error_status", "field_type_changed"
drift.field         # WHAT changed (field path or "latency_p95", "status:429", ...)
drift.from_value    # FROM what
drift.to_value      # TO what
drift.confidence    # 0.0–1.0
drift.detected_at   # WHEN
drift.endpoint      # AFFECTED ENDPOINT
```

### Proxy mode (zero code changes in the client)

```python
from abf import Recorder, FingerprintingProxy
from abf.storage import SQLiteStorage

recorder = Recorder(SQLiteStorage("abf.db"))
proxy = FingerprintingProxy(target_base_url="https://api.example.com", recorder=recorder)
proxy.serve(port=8089)  # point your client at http://localhost:8089 instead
```

### CLI

```bash
abf fingerprint "GET /users/{id}" --label baseline --db abf.db
# ... record more traffic later, e.g. after a deploy ...
abf fingerprint "GET /users/{id}" --label current --db abf.db
abf compare "GET /users/{id}" --baseline baseline --current current --db abf.db
abf detect --baseline baseline --current current --db abf.db   # across all endpoints
abf explain "GET /users/{id}" --baseline baseline --current current --db abf.db
```

## Design principles

- **Behavior over schema.** Schema diffing is table stakes; this project's
  reason to exist is catching drift schema diffing can't see.
- **Every finding is classified.** `schema_drift` vs `behavior_drift` is
  not a nuance — it's the primary axis of the whole model.
- **No SaaS dashboard.** A small, reliable, composable core: recorder,
  fingerprint engine, comparison engine, CLI. JSON in, JSON/text out.
- **Local-first.** SQLite by default, proxy mode needs no external
  dependency at all.
- **Confidence, not certainty.** Every drift record carries a confidence
  score — thresholds are deliberately conservative to avoid noisy false
  positives on small sample sizes.

## Project layout

```
src/abf/
  models.py    Observation, FieldShape, EndpointFingerprint, DriftRecord
  recorder.py  Recorder — turns raw HTTP exchanges into Observations; path normalization
  storage.py   StorageBackend protocol + SQLiteStorage + InMemoryStorage
  compare.py   compare_fingerprints() — schema vs. behavior drift detection
  proxy.py     FingerprintingProxy — stdlib-only recording reverse proxy
  cli.py       `abf` command-line tool
tests/         pytest suite
examples/      runnable example scripts
```

## Status

Alpha / MVP. Recording, fingerprinting, comparison, drift classification,
CLI, and the proxy are implemented and tested. Not yet implemented: an
`httpx` client wrapper for automatic in-process recording (the raw
recorder API covers this today with one extra line), and a hosted
dashboard (intentionally out of scope).

## License

MIT
