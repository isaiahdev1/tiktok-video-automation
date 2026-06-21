"""Send failure/status alerts to a webhook so silent outages can't happen.

Set ALERT_WEBHOOK to a Discord or Slack incoming-webhook URL. If unset, this
no-ops silently, so the pipeline behaves exactly as before when not configured.
"""

from __future__ import annotations
import os

import requests


def notify(message: str, ok: bool = False) -> None:
    """Post a short status line to ALERT_WEBHOOK. Never raises."""
    url = os.environ.get("ALERT_WEBHOOK", "").strip()
    if not url:
        return

    channel = os.environ.get("CHANNEL_NAME", "shorts pipeline")
    icon = "✅" if ok else "🚨"
    text = f"{icon} [{channel}] {message}"

    try:
        # Slack uses {"text": ...}; Discord uses {"content": ...}. Send both
        # keys so a single helper works for either provider.
        requests.post(url, json={"text": text, "content": text}, timeout=10)
    except Exception as e:  # alerting must never break the run
        print(f"[notify] Failed to send alert: {e}")
