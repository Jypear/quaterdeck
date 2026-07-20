"""Token-gated Prometheus metrics endpoint.

If METRICS_TOKEN is unset, /metrics is open (matches the app's "open on a
private network" REQUIRE_LOGIN=False philosophy). If set, requires a matching
`Authorization: Bearer <token>` header.
"""

from __future__ import annotations

import hmac
import os
from typing import TYPE_CHECKING

from django.http import HttpResponse
from django_prometheus.exports import ExportToDjangoView

if TYPE_CHECKING:
    from django.http import HttpRequest


# ponytail: single-process registry (prometheus_client default). Gunicorn runs
# one worker today so this is accurate. If workers are ever scaled up, switch
# to prometheus_client multiprocess mode (PROMETHEUS_MULTIPROC_DIR).
def metrics_view(request: HttpRequest) -> HttpResponse:
    token = os.environ.get("METRICS_TOKEN")
    if token and not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
        return HttpResponse("Unauthorized", status=401)
    return ExportToDjangoView(request)
