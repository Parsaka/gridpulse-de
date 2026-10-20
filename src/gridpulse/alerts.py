"""Alert delivery over a generic webhook (Slack, Teams, Mattermost, Discord, or any receiver).

The payload carries the message under both `text` (Slack/Teams/Mattermost) and `content`
(Discord). Delivery never raises: an alerting problem must not break the task that is reporting.
"""

import logging

import httpx

from gridpulse.config import get_settings

log = logging.getLogger(__name__)


def send_alert(text: str, url: str | None = None, timeout: float = 5.0) -> bool:
    """POST the alert; return True when the receiver accepted it."""
    url = url or get_settings().alert_webhook
    if not url:
        log.warning("alert not delivered (GRIDPULSE_ALERT_WEBHOOK is not set): %s", text)
        return False
    try:
        httpx.post(url, json={"text": text, "content": text}, timeout=timeout).raise_for_status()
        return True
    except Exception:
        log.exception("alert delivery failed: %s", text)
        return False
