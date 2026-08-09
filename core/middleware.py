"""Middleware that optionally gates the entire app behind session auth, plus
HTMX support middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.template.loader import render_to_string

from core.tables import is_partial

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

# Paths that are always public, regardless of REQUIRE_LOGIN.
_PUBLIC_PREFIXES = (
    settings.LOGIN_URL,
    "/admin/",
    "/static/",
    "/webhooks/inbound/",  # authenticated by HMAC signature instead of a session
    "/metrics",  # scraped by Prometheus without a session; gated by METRICS_TOKEN instead
)


class RequireLoginMiddleware:
    """Redirect unauthenticated requests to the login page when the
    Settings.require_login flag is enabled."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self._is_public(request.path) and self._login_required() and not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return self.get_response(request)

    @staticmethod
    def _is_public(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)

    @staticmethod
    def _login_required() -> bool:
        # Import here to avoid AppRegistryNotReady at module load time.
        from core.models import Settings

        try:
            return Settings.get().require_login
        except Exception:
            return False


class HtmxMessagesMiddleware:
    """Render queued messages into htmx partial responses as an out-of-band swap.

    Partials don't extend base.html, so they never iterate the message storage —
    the message would otherwise sit unconsumed and surface on whatever full page
    the user loads next instead of the one that triggered it (issue #13).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if (
            is_partial(request)
            and response.status_code == 200
            and response.get("Content-Type", "").startswith("text/html")
            and hasattr(response, "content")
        ):
            storage = messages.get_messages(request)
            if not storage.used and len(storage):
                response.write(render_to_string("_messages.html", {"messages": storage, "oob": True}, request))
        return response
