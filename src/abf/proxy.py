"""HTTP proxy mode: a minimal forwarding reverse proxy, built on the
standard library only, that records every response it forwards as an
Observation. Point your client at this proxy instead of the real API to
start fingerprinting traffic with zero code changes.

    proxy = FingerprintingProxy(target_base_url="https://api.example.com", recorder=recorder)
    proxy.serve(port=8089)  # blocking; run in a thread/process for real use
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .recorder import Recorder


def _make_handler(target_base_url: str, recorder: Recorder) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _forward(self, method: str) -> None:
            target_url = target_base_url.rstrip("/") + self.path
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else None

            headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
            req = urllib.request.Request(target_url, data=body, headers=headers, method=method)

            start = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status = resp.status
                    resp_headers = dict(resp.getheaders())
                    resp_body = resp.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                resp_headers = dict(exc.headers or {})
                resp_body = exc.read()
            latency_ms = (time.perf_counter() - start) * 1000

            content_type = resp_headers.get("Content-Type")
            json_body = None
            if content_type and "json" in content_type and resp_body:
                try:
                    json_body = json.loads(resp_body)
                except json.JSONDecodeError:
                    json_body = None

            recorder.record_raw(
                method,
                self.path.split("?", 1)[0],
                status,
                latency_ms,
                request_headers=headers,
                response_headers=resp_headers,
                content_type=content_type,
                json_body=json_body,
            )

            self.send_response(status)
            for key, value in resp_headers.items():
                if key.lower() in {"content-length", "transfer-encoding", "connection"}:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        def do_GET(self) -> None:
            self._forward("GET")

        def do_POST(self) -> None:
            self._forward("POST")

        def do_PUT(self) -> None:
            self._forward("PUT")

        def do_PATCH(self) -> None:
            self._forward("PATCH")

        def do_DELETE(self) -> None:
            self._forward("DELETE")

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep stdout clean; the recorder is the source of truth

    return Handler


class FingerprintingProxy:
    """A forwarding proxy that fingerprints every response it relays."""

    def __init__(self, target_base_url: str, recorder: Recorder) -> None:
        self.target_base_url = target_base_url
        self.recorder = recorder
        self._server: ThreadingHTTPServer | None = None

    def serve(self, host: str = "127.0.0.1", port: int = 8089) -> None:
        """Blocking call — run this in its own thread/process."""
        handler_cls = _make_handler(self.target_base_url, self.recorder)
        self._server = ThreadingHTTPServer((host, port), handler_cls)
        try:
            self._server.serve_forever()
        finally:
            self._server.server_close()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
