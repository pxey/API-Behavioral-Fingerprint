"""Recording engine: turns a raw HTTP exchange into an :class:`Observation`.

Framework-agnostic by design — :meth:`Recorder.record_raw` takes plain
Python values (status code, headers, body, latency) so it works whether
the exchange came from ``httpx``, ``requests``, the stdlib, or the proxy.
An optional :meth:`Recorder.record_httpx_response` convenience wrapper is
provided for callers who have ``httpx`` installed.
"""

from __future__ import annotations

import re
from typing import Any

from .models import Observation
from .storage import StorageBackend

_PAGINATION_HINTS = {"next", "cursor", "page", "page_token", "next_cursor", "has_more", "offset", "limit"}
_ID_SEGMENT_RE = re.compile(r"^\d+$|^[0-9a-fA-F-]{8,}$")


def normalize_path(path: str) -> str:
    """Collapse likely-dynamic path segments (numeric ids, UUIDs) into a
    template so 'GET /users/123' and 'GET /users/456' fingerprint together.
    """
    segments = [s for s in path.split("/") if s != ""]
    normalized = ["{id}" if _ID_SEGMENT_RE.match(s) else s for s in segments]
    return "/" + "/".join(normalized)


def _flatten_json_types(value: Any, prefix: str = "") -> dict[str, str]:
    """Flatten a JSON value into {dotted.path: json_type_name}."""
    result: dict[str, str] = {}
    if isinstance(value, dict):
        if not value:
            result[prefix or "$"] = "object"
        for key, sub in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(_flatten_json_types(sub, path))
    elif isinstance(value, list):
        result[prefix or "$"] = "array"
        if value:
            result.update(_flatten_json_types(value[0], f"{prefix}[]" if prefix else "[]"))
    elif value is None:
        result[prefix or "$"] = "null"
    elif isinstance(value, bool):
        result[prefix or "$"] = "bool"
    elif isinstance(value, int):
        result[prefix or "$"] = "int"
    elif isinstance(value, float):
        result[prefix or "$"] = "float"
    elif isinstance(value, str):
        result[prefix or "$"] = "string"
    else:
        result[prefix or "$"] = type(value).__name__
    return result


class Recorder:
    """Records HTTP exchanges into observations and persists them."""

    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    def record_raw(
        self,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        *,
        request_headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
        content_type: str | None = None,
        json_body: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Observation:
        endpoint = f"{method.upper()} {normalize_path(path)}"
        body_fields = _flatten_json_types(json_body) if json_body is not None else {}
        pagination_keys: set[str] = set()
        if isinstance(json_body, dict):
            pagination_keys = {k for k in json_body.keys() if k.lower() in _PAGINATION_HINTS}

        obs = Observation(
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=latency_ms,
            request_headers=request_headers or {},
            response_headers=response_headers or {},
            content_type=content_type,
            body_fields=body_fields,
            pagination_keys=pagination_keys,
            is_error=status_code >= 400,
            metadata=metadata or {},
        )
        self.storage.save_observation(obs)
        return obs

    def record_httpx_response(self, method: str, path: str, response: Any, latency_ms: float) -> Observation:
        """Convenience wrapper for an ``httpx.Response``-like object
        (anything with ``.status_code``, ``.headers``, and ``.json()``).
        Import of httpx itself is never required by this module.
        """
        json_body: Any = None
        try:
            json_body = response.json()
        except Exception:
            json_body = None
        headers = dict(response.headers)
        return self.record_raw(
            method,
            path,
            response.status_code,
            latency_ms,
            response_headers=headers,
            content_type=headers.get("content-type"),
            json_body=json_body,
        )
