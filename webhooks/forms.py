"""HTML forms for webhook endpoint CRUD."""

from __future__ import annotations

from typing import ClassVar

from django import forms

from core.forms import BootstrapModelForm
from webhooks.models import EVENT_CHOICES, WebhookEndpoint


class WebhookEndpointForm(BootstrapModelForm):
    event_types = forms.MultipleChoiceField(
        choices=EVENT_CHOICES,
        required=False,
        widget=forms.SelectMultiple,
        help_text="Select none to receive all events.",
    )

    class Meta:
        model = WebhookEndpoint
        fields: ClassVar[list[str]] = ["url", "event_types", "is_active"]
