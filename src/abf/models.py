"""Core domain model for API Behavioral Fingerprint.

    Request -> Response -> Behavioral Observation -> Fingerprint
            -> Historical Comparison -> Drift Detection

A single HTTP exchange becomes an :class:`Observation`. Many observations
for the same endpoint are aggregated into an :class:`EndpointFingerprint` —
a statistical/structural summary of how that endpoint actually behaves.
Comparing two fingerprints (old baseline vs. new) produces
:class:`DriftRecord` entries, each tagged as schema drift or behavior
drift.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FieldShape(BaseModel):
    """Structural summary of one JSON field path across many observations."""

    path: str
    json_types: set[str] = Field(default_factory=set)
    present_count: int = 0
    nullable: bool = False

    def present_rate(self, sample_count: int) -> float:
        return self.present_count / sample_count if sample_count else 0.0


class Observation(BaseModel):
    """A single recorded HTTP exchange."""

    id: str = Field(default_factory=lambda: _new_id("obs"))
    endpoint: str
    """Normalized method + path template, e.g. 'GET /users/{id}'."""
    timestamp: datetime = Field(default_factory=_utcnow)
    status_code: int
    latency_ms: float
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)
    content_type: str | None = None
    body_fields: dict[str, str] = Field(default_factory=dict)
    """Flattened dotted-path -> JSON type name, e.g. {'user.id': 'int'}."""
    pagination_keys: set[str] = Field(default_factory=set)
    """Keys observed that look pagination-related (next, cursor, page, ...)."""
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EndpointFingerprint(BaseModel):
    """Aggregated behavioral summary for one endpoint over N observations."""

    endpoint: str
    sample_count: int
    computed_at: datetime = Field(default_factory=_utcnow)
    status_codes: dict[int, int] = Field(default_factory=dict)
    fields: dict[str, FieldShape] = Field(default_factory=dict)
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    content_types: dict[str, int] = Field(default_factory=dict)
    response_header_keys: set[str] = Field(default_factory=set)
    pagination_keys: set[str] = Field(default_factory=set)
    error_rate: float = 0.0

    @classmethod
    def from_observations(cls, endpoint: str, observations: list[Observation]) -> EndpointFingerprint:
        n = len(observations)
        status_codes: dict[int, int] = {}
        fields: dict[str, FieldShape] = {}
        content_types: dict[str, int] = {}
        header_keys: set[str] = set()
        pagination_keys: set[str] = set()
        latencies: list[float] = []
        error_count = 0

        for obs in observations:
            status_codes[obs.status_code] = status_codes.get(obs.status_code, 0) + 1
            if obs.content_type:
                content_types[obs.content_type] = content_types.get(obs.content_type, 0) + 1
            header_keys |= set(obs.response_headers.keys())
            pagination_keys |= obs.pagination_keys
            latencies.append(obs.latency_ms)
            if obs.is_error:
                error_count += 1
            for path, json_type in obs.body_fields.items():
                shape = fields.setdefault(path, FieldShape(path=path))
                shape.json_types.add(json_type)
                shape.present_count += 1
                if json_type == "null":
                    shape.nullable = True

        latencies.sort()

        def percentile(p: float) -> float:
            if not latencies:
                return 0.0
            k = max(0, min(len(latencies) - 1, round(p * (len(latencies) - 1))))
            return latencies[k]

        return cls(
            endpoint=endpoint,
            sample_count=n,
            status_codes=status_codes,
            fields=fields,
            latency_p50=percentile(0.50),
            latency_p95=percentile(0.95),
            latency_p99=percentile(0.99),
            content_types=content_types,
            response_header_keys=header_keys,
            pagination_keys=pagination_keys,
            error_rate=(error_count / n) if n else 0.0,
        )


class DriftCategory(str, Enum):
    SCHEMA = "schema_drift"
    BEHAVIOR = "behavior_drift"


class DriftKind(str, Enum):
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    FIELD_BECAME_OPTIONAL = "field_became_optional"
    FIELD_BECAME_REQUIRED = "field_became_required"
    STATUS_DISTRIBUTION_CHANGED = "status_distribution_changed"
    NEW_ERROR_STATUS = "new_error_status"
    LATENCY_CHANGED = "latency_changed"
    CONTENT_TYPE_CHANGED = "content_type_changed"
    PAGINATION_CHANGED = "pagination_changed"
    ERROR_RATE_CHANGED = "error_rate_changed"


_SCHEMA_KINDS = {
    DriftKind.FIELD_ADDED,
    DriftKind.FIELD_REMOVED,
    DriftKind.FIELD_TYPE_CHANGED,
    DriftKind.FIELD_BECAME_OPTIONAL,
    DriftKind.FIELD_BECAME_REQUIRED,
}


class DriftRecord(BaseModel):
    """Answers: WHAT changed, WHEN, FROM what, TO what, with what
    CONFIDENCE, on which endpoint.
    """

    id: str = Field(default_factory=lambda: _new_id("drift"))
    endpoint: str
    kind: DriftKind
    category: DriftCategory
    field: str | None = None
    from_value: str
    to_value: str
    confidence: float
    detected_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        endpoint: str,
        kind: DriftKind,
        from_value: Any,
        to_value: Any,
        confidence: float,
        field: str | None = None,
    ) -> DriftRecord:
        category = DriftCategory.SCHEMA if kind in _SCHEMA_KINDS else DriftCategory.BEHAVIOR
        return cls(
            endpoint=endpoint,
            kind=kind,
            category=category,
            field=field,
            from_value=str(from_value),
            to_value=str(to_value),
            confidence=confidence,
        )

    def explain(self) -> str:
        where = f" field '{self.field}'" if self.field else ""
        return (
            f"[{self.category.value}] {self.endpoint}{where}: "
            f"{self.kind.value} — from '{self.from_value}' to '{self.to_value}' "
            f"(confidence={self.confidence:.2f}, detected_at={self.detected_at.isoformat()})"
        )
