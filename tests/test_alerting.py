"""
test_alerting.py

Tests monitoring/alerting.py: always logs, and POSTs to a webhook only
when one is configured. Uses a real local HTTP server (not a mocked
requests call) to prove delivery actually happens over the network, the
same way the manual verification during development did.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from monitoring.alerting import send_alert


class _RecordingHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        _RecordingHandler.received.append(body)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # keep test output quiet


@pytest.fixture
def local_webhook_server():
    _RecordingHandler.received = []
    server = HTTPServer(("localhost", 0), _RecordingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{port}/webhook", _RecordingHandler.received
    server.shutdown()


def test_send_alert_without_webhook_configured_does_not_raise(monkeypatch, caplog):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    with caplog.at_level("INFO"):
        send_alert("no webhook configured", severity="info")
    assert "no webhook configured" in caplog.text


def test_send_alert_posts_to_configured_webhook(local_webhook_server, monkeypatch):
    url, received = local_webhook_server
    monkeypatch.setenv("ALERT_WEBHOOK_URL", url)

    send_alert("drift detected on model X", severity="warning")

    assert len(received) == 1
    assert "WARNING" in received[0]["text"]
    assert "drift detected on model X" in received[0]["text"]


def test_send_alert_severity_levels_all_deliver(local_webhook_server, monkeypatch):
    url, received = local_webhook_server
    monkeypatch.setenv("ALERT_WEBHOOK_URL", url)

    for severity in ("info", "warning", "critical"):
        send_alert(f"{severity} level test", severity=severity)

    assert len(received) == 3
    severities_seen = {body["text"].split("]")[0].strip("[") for body in received}
    assert severities_seen == {"INFO", "WARNING", "CRITICAL"}


def test_send_alert_webhook_failure_does_not_raise(monkeypatch, caplog):
    """An unreachable webhook must not crash the caller - the alert is
    already logged regardless of delivery success."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://localhost:1/unreachable-port")
    send_alert("this should still log even though delivery fails", severity="critical")
    assert "this should still log even though delivery fails" in caplog.text
