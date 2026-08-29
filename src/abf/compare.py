"""Comparison and drift detection engine.

Compares a baseline :class:`EndpointFingerprint` against a current one and
produces :class:`DriftRecord` entries. Every drift kind is explicitly
classified as ``schema_drift`` (the shape of the data changed) or
``behavior_drift`` (how the endpoint behaves changed, independent of
schema) — this is the distinction the whole project exists to make.
"""

from __future__ import annotations

from .models import DriftKind, DriftRecord, EndpointFingerprint

# A latency change below this ratio is considered noise, not drift.
_LATENCY_DRIFT_THRESHOLD = 0.30
# A status-code share change below this (in percentage points) is noise.
_STATUS_SHARE_THRESHOLD = 0.10
_ERROR_RATE_THRESHOLD = 0.10
_PRESENCE_RATE_THRESHOLD = 0.05


def compare_fingerprints(baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    if baseline.endpoint != current.endpoint:
        raise ValueError("Cannot compare fingerprints for different endpoints")

    drifts: list[DriftRecord] = []
    endpoint = current.endpoint

    drifts.extend(_field_drift(endpoint, baseline, current))
    drifts.extend(_status_drift(endpoint, baseline, current))
    drifts.extend(_latency_drift(endpoint, baseline, current))
    drifts.extend(_content_type_drift(endpoint, baseline, current))
    drifts.extend(_pagination_drift(endpoint, baseline, current))
    drifts.extend(_error_rate_drift(endpoint, baseline, current))

    return drifts


def _field_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    drifts: list[DriftRecord] = []
    base_fields, cur_fields = baseline.fields, current.fields

    for path, cur_shape in cur_fields.items():
        base_shape = base_fields.get(path)
        if base_shape is None:
            drifts.append(
                DriftRecord.create(endpoint, DriftKind.FIELD_ADDED, "absent", "present", confidence=0.9, field=path)
            )
            continue

        if cur_shape.json_types != base_shape.json_types:
            drifts.append(
                DriftRecord.create(
                    endpoint,
                    DriftKind.FIELD_TYPE_CHANGED,
                    sorted(base_shape.json_types),
                    sorted(cur_shape.json_types),
                    confidence=0.85,
                    field=path,
                )
            )

        base_rate = base_shape.present_rate(baseline.sample_count)
        cur_rate = cur_shape.present_rate(current.sample_count)
        if base_rate - cur_rate > _PRESENCE_RATE_THRESHOLD and base_rate > 0.95 and cur_rate < 0.95:
            drifts.append(
                DriftRecord.create(
                    endpoint,
                    DriftKind.FIELD_BECAME_OPTIONAL,
                    f"{base_rate:.0%} present",
                    f"{cur_rate:.0%} present",
                    confidence=0.6,
                    field=path,
                )
            )
        elif cur_rate - base_rate > _PRESENCE_RATE_THRESHOLD and cur_rate > 0.95 and base_rate < 0.95:
            drifts.append(
                DriftRecord.create(
                    endpoint,
                    DriftKind.FIELD_BECAME_REQUIRED,
                    f"{base_rate:.0%} present",
                    f"{cur_rate:.0%} present",
                    confidence=0.6,
                    field=path,
                )
            )

    for path, base_shape in base_fields.items():
        if path not in cur_fields:
            drifts.append(
                DriftRecord.create(
                    endpoint, DriftKind.FIELD_REMOVED, "present", "absent", confidence=0.9, field=path
                )
            )

    return drifts


def _status_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    drifts: list[DriftRecord] = []
    base_total = baseline.sample_count or 1
    cur_total = current.sample_count or 1
    all_codes = set(baseline.status_codes) | set(current.status_codes)

    for code in sorted(all_codes):
        base_share = baseline.status_codes.get(code, 0) / base_total
        cur_share = current.status_codes.get(code, 0) / cur_total
        if code not in baseline.status_codes and code in current.status_codes and code >= 400:
            drifts.append(
                DriftRecord.create(
                    endpoint,
                    DriftKind.NEW_ERROR_STATUS,
                    "never observed",
                    f"{cur_share:.0%} of responses",
                    confidence=0.8,
                    field=f"status:{code}",
                )
            )
        elif abs(base_share - cur_share) >= _STATUS_SHARE_THRESHOLD:
            drifts.append(
                DriftRecord.create(
                    endpoint,
                    DriftKind.STATUS_DISTRIBUTION_CHANGED,
                    f"{base_share:.0%}",
                    f"{cur_share:.0%}",
                    confidence=0.6,
                    field=f"status:{code}",
                )
            )
    return drifts


def _latency_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    if baseline.latency_p95 <= 0:
        return []
    ratio = (current.latency_p95 - baseline.latency_p95) / baseline.latency_p95
    if abs(ratio) < _LATENCY_DRIFT_THRESHOLD:
        return []
    confidence = min(0.95, 0.5 + abs(ratio))
    return [
        DriftRecord.create(
            endpoint,
            DriftKind.LATENCY_CHANGED,
            f"p95={baseline.latency_p95:.0f}ms",
            f"p95={current.latency_p95:.0f}ms",
            confidence=confidence,
            field="latency_p95",
        )
    ]


def _content_type_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    base_types = set(baseline.content_types)
    cur_types = set(current.content_types)
    if base_types == cur_types:
        return []
    return [
        DriftRecord.create(
            endpoint,
            DriftKind.CONTENT_TYPE_CHANGED,
            sorted(base_types),
            sorted(cur_types),
            confidence=0.8,
            field="content_type",
        )
    ]


def _pagination_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    if baseline.pagination_keys == current.pagination_keys:
        return []
    return [
        DriftRecord.create(
            endpoint,
            DriftKind.PAGINATION_CHANGED,
            sorted(baseline.pagination_keys),
            sorted(current.pagination_keys),
            confidence=0.7,
            field="pagination",
        )
    ]


def _error_rate_drift(endpoint: str, baseline: EndpointFingerprint, current: EndpointFingerprint) -> list[DriftRecord]:
    if abs(current.error_rate - baseline.error_rate) < _ERROR_RATE_THRESHOLD:
        return []
    return [
        DriftRecord.create(
            endpoint,
            DriftKind.ERROR_RATE_CHANGED,
            f"{baseline.error_rate:.0%}",
            f"{current.error_rate:.0%}",
            confidence=0.65,
            field="error_rate",
        )
    ]
