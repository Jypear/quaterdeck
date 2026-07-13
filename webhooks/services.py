"""Outbound webhook delivery: signing, dispatch, and delivery logging.

Uses stdlib only (hmac/hashlib/urllib/threading) — no task queue. Delivery
runs in a background thread per endpoint so a slow or dead receiver never
blocks the request that triggered the event.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

from django.db import connection

if TYPE_CHECKING:
    from webhooks.models import WebhookEndpoint

_TIMEOUT_SECONDS = 5


def sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(secret: str, body: bytes, header: str) -> bool:
    return hmac.compare_digest(sign(secret, body), header or "")


def dispatch_event(event_type: str, payload: dict[str, Any]) -> None:
    """Fire `event_type` to every active endpoint subscribed to it."""
    from webhooks.models import WebhookEndpoint  # deferred: avoid import-time app-registry issues

    for endpoint in WebhookEndpoint.objects.filter(is_active=True):
        if endpoint.subscribes_to(event_type):
            threading.Thread(target=_deliver, args=(endpoint, event_type, payload), daemon=True).start()


def _deliver(endpoint: WebhookEndpoint, event_type: str, payload: dict[str, Any]) -> None:
    # ponytail: fire-and-forget thread, no retry/backoff. Add a task queue
    # (Celery/RQ) if delivery reliability or retries matter.
    from webhooks.models import WebhookDelivery

    body = json.dumps({"event": event_type, "data": payload}, default=str).encode()
    status_code: int | None = None
    error = ""
    try:
        request = urllib.request.Request(
            endpoint.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Quaterdeck-Event": event_type,
                "X-Quaterdeck-Signature": sign(endpoint.secret, body),
            },
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error = str(exc)
    except Exception as exc:
        error = str(exc)

    try:
        WebhookDelivery.objects.create(
            endpoint=endpoint,
            event_type=event_type,
            payload=payload,
            status_code=status_code,
            success=status_code is not None and 200 <= status_code < 300,
            error=error,
        )
    finally:
        # This runs in a thread of its own — release its DB connection rather
        # than leaving it idle until garbage collection.
        connection.close()
