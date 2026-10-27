"""Storage for observations and computed fingerprints. SQLite by default,
InMemory for tests — same pattern as the other engines in this family.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import EndpointFingerprint, Observation


class StorageBackend(Protocol):
    def save_observation(self, obs: Observation) -> None: ...

    def observations_for(self, endpoint: str) -> list[Observation]: ...

    def all_observations(self) -> list[Observation]: ...

    def endpoints(self) -> list[str]: ...

    def save_fingerprint(self, fp: EndpointFingerprint, label: str) -> None: ...

    def get_fingerprint(self, endpoint: str, label: str) -> EndpointFingerprint | None: ...

    def close(self) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_endpoint ON observations(endpoint);

CREATE TABLE IF NOT EXISTS fingerprints (
    endpoint TEXT NOT NULL,
    label TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (endpoint, label)
);
"""


class SQLiteStorage:
    def __init__(self, path: str | Path = "abf.db") -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_observation(self, obs: Observation) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO observations (id, endpoint, payload) VALUES (?, ?, ?)",
            (obs.id, obs.endpoint, obs.model_dump_json()),
        )
        self._conn.commit()

    def observations_for(self, endpoint: str) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT payload FROM observations WHERE endpoint = ?", (endpoint,)
        ).fetchall()
        return [Observation.model_validate_json(r[0]) for r in rows]

    def all_observations(self) -> list[Observation]:
        rows = self._conn.execute("SELECT payload FROM observations").fetchall()
        return [Observation.model_validate_json(r[0]) for r in rows]

    def endpoints(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT endpoint FROM observations").fetchall()
        return [r[0] for r in rows]

    def save_fingerprint(self, fp: EndpointFingerprint, label: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO fingerprints (endpoint, label, payload) VALUES (?, ?, ?)",
            (fp.endpoint, label, fp.model_dump_json()),
        )
        self._conn.commit()

    def get_fingerprint(self, endpoint: str, label: str) -> EndpointFingerprint | None:
        row = self._conn.execute(
            "SELECT payload FROM fingerprints WHERE endpoint = ? AND label = ?", (endpoint, label)
        ).fetchone()
        return EndpointFingerprint.model_validate_json(row[0]) if row else None

    def close(self) -> None:
        self._conn.close()


class InMemoryStorage:
    def __init__(self) -> None:
        self._observations: list[Observation] = []
        self._fingerprints: dict[tuple[str, str], EndpointFingerprint] = {}

    def save_observation(self, obs: Observation) -> None:
        self._observations.append(obs)

    def observations_for(self, endpoint: str) -> list[Observation]:
        return [o for o in self._observations if o.endpoint == endpoint]

    def all_observations(self) -> list[Observation]:
        return list(self._observations)

    def endpoints(self) -> list[str]:
        return sorted({o.endpoint for o in self._observations})

    def save_fingerprint(self, fp: EndpointFingerprint, label: str) -> None:
        self._fingerprints[(fp.endpoint, label)] = fp

    def get_fingerprint(self, endpoint: str, label: str) -> EndpointFingerprint | None:
        return self._fingerprints.get((endpoint, label))

    def close(self) -> None:
        pass
