"""Webhook endpoint CRUD (outbound) and the inbound receiver endpoint.

CRUD mirrors notes/views.py::_NoteFormMixin — plain full-page forms, not HTMX
modals. The inbound view is deliberately a plain function view, not DRF:
signature verification IS the auth, and an external caller has no session to
authenticate with.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.models import Settings
from tasks.models import Task
from webhooks.forms import WebhookEndpointForm
from webhooks.models import WebhookDelivery, WebhookEndpoint
from webhooks.services import verify

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse


class WebhookEndpointListView(ListView):
    model = WebhookEndpoint
    template_name = "webhooks/list.html"
    context_object_name = "endpoints"


class _WebhookFormMixin:
    """Shared template + page title + success message, matching notes/tasks CRUD."""

    template_name = "webhooks/_form.html"
    success_message = "Saved."
    success_url = reverse_lazy("webhooks:list")
    title = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("title", self.title)
        context.setdefault("cancel_url", reverse_lazy("webhooks:list"))
        return context

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class WebhookEndpointCreateView(_WebhookFormMixin, CreateView):
    model = WebhookEndpoint
    form_class = WebhookEndpointForm
    title = "Add webhook endpoint"


class WebhookEndpointUpdateView(_WebhookFormMixin, UpdateView):
    model = WebhookEndpoint
    form_class = WebhookEndpointForm
    title = "Edit webhook endpoint"


class WebhookEndpointDeleteView(DeleteView):
    model = WebhookEndpoint
    template_name = "webhooks/_confirm_delete.html"
    success_url = reverse_lazy("webhooks:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.success_url)
        return context


class WebhookDeliveryListView(ListView):
    """Read-only recent delivery log — nothing to create/edit here."""

    model = WebhookDelivery
    template_name = "webhooks/deliveries.html"
    context_object_name = "deliveries"
    paginate_by = 50
    queryset = WebhookDelivery.objects.select_related("endpoint")


def _create_task(data: dict[str, Any]) -> dict[str, Any]:
    task = Task.objects.create(
        title=data.get("title", ""),
        due_date=data.get("due_date") or None,
        priority=data.get("priority") or Task.Priority.MEDIUM,
        budget_amount=data.get("budget_amount") or None,
    )
    return {"id": task.pk}


# ponytail: one inbound handler (create_task). Add handlers to this dict as
# concrete external integrations appear — YAGNI on the rest.
_INBOUND_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "create_task": _create_task,
}


@csrf_exempt
@require_POST
def inbound(request: HttpRequest) -> HttpResponse:
    """External services POST here (`{"type": ..., ...}`) to create records.

    Authenticated purely by HMAC signature (X-Quaterdeck-Signature) against
    Settings.webhook_inbound_secret — an external caller has no Django
    session to hold, so this sits outside DRF's session auth deliberately.
    """
    secret = Settings.get().webhook_inbound_secret
    signature = request.headers.get("X-Quaterdeck-Signature", "")
    if not secret or not verify(secret, request.body, signature):
        return JsonResponse({"error": "invalid signature"}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("invalid JSON")

    handler = _INBOUND_HANDLERS.get(data.get("type"))
    if handler is None:
        return HttpResponseBadRequest("unknown type")

    return JsonResponse(handler(data), status=201)
