"""
monitoring/alerting.py

Milestone 11: minimal alert dispatcher. Every alert always gets logged
(so nothing is ever silently dropped just because a webhook isn't
configured); if config.yaml's monitoring.alert_webhook_url_env_var
names a set environment variable (e.g. a Slack incoming webhook URL),
the alert is also POSTed there as a Slack-compatible {"text": ...}
payload - the same minimal JSON shape Slack, Discord (via a
Slack-compatible endpoint), and most "generic webhook" integrations
accept, so this isn't locked to one specific tool.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import requests

from config.config_loader import load_config

logger = logging.getLogger(__name__)

Severity = Literal["info", "warning", "critical"]

_LOG_LEVEL_BY_SEVERITY = {
    "info": logging.INFO,
    "warning": logging.WARNING,
    "critical": logging.ERROR,
}


def send_alert(message: str, severity: Severity = "warning", config: dict | None = None) -> None:
    """Log the alert, and POST it to a webhook if one is configured."""
    config = config or load_config()
    logger.log(_LOG_LEVEL_BY_SEVERITY[severity], "[ALERT:%s] %s", severity.upper(), message)

    webhook_env_var = config.get("monitoring", {}).get("alert_webhook_url_env_var", "ALERT_WEBHOOK_URL")
    webhook_url = os.environ.get(webhook_env_var)
    if not webhook_url:
        return

    try:
        response = requests.post(
            webhook_url,
            json={"text": f"[{severity.upper()}] AI Model Insight Platform: {message}"},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        # A failed webhook delivery must never mask the alert itself -
        # it's already logged above regardless of what happens here.
        logger.warning("Failed to deliver alert to webhook: %s", exc)
