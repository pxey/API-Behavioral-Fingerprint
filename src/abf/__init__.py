"""API Behavioral Fingerprint.

Detects undocumented behavioral changes in APIs by observing real request
and response traffic — status behavior, response shape, headers, latency,
pagination, errors, and content types — and clearly distinguishes
**schema drift** (the data shape changed) from **behavior drift** (how the
endpoint behaves changed, independent of schema).

Quick start::

    from abf import Recorder, EndpointFingerprint, compare_fingerprints
    from abf.storage import InMemoryStorage

    storage = InMemoryStorage()
    recorder = Recorder(storage)

    recorder.record_raw("GET", "/users/123", 200, latency_ms=42.0,
                         json_body={"id": 123, "name": "Ada"})

    obs = storage.observations_for("GET /users/{id}")
    fp = EndpointFingerprint.from_observations("GET /users/{id}", obs)
"""

from .compare import compare_fingerprints
from .models import (
    DriftCategory,
    DriftKind,
    DriftRecord,
    EndpointFingerprint,
    FieldShape,
    Observation,
)
from .proxy import FingerprintingProxy
from .recorder import Recorder, normalize_path
from .storage import InMemoryStorage, SQLiteStorage, StorageBackend

__version__ = "0.1.0"

__all__ = [
    "Recorder",
    "normalize_path",
    "Observation",
    "FieldShape",
    "EndpointFingerprint",
    "DriftKind",
    "DriftCategory",
    "DriftRecord",
    "compare_fingerprints",
    "FingerprintingProxy",
    "StorageBackend",
    "SQLiteStorage",
    "InMemoryStorage",
    "__version__",
]
