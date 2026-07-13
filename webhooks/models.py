"""Webhook models: outbound subscriptions and their delivery log.

Inbound webhooks have no model of their own — they're authenticated against
Settings.webhook_inbound_secret (core/models.py) and handled directly in
webhooks/views.py.
"""

from __future__ import annotations

import secrets
from typing import Any

from django.db import models
from django.urls import reverse

EVENT_CHOICES = [
    ("task.created", "Task created"),
    ("task.updated", "Task updated"),
    ("task.deleted", "Task deleted"),
    ("pot.created", "Pot created"),
    ("pot.updated", "Pot updated"),
    ("note.created", "Note created"),
    ("oneoff.created", "One-off outgoing created"),
]


class WebhookEndpoint(models.Model):
    """An external URL subscribed to Quaterdeck domain events.

    Single-user instance, so the signing secret is shown to the owner in the
    UI rather than write-only masked — they're the only one who'll ever POST
    the receiving side.
    """

    url = models.URLField()
    event_types = models.JSONField(default=list, blank=True, help_text="Leave empty to receive all events.")
    secret = models.CharField(max_length=64, blank=True, help_text="Auto-generated if left blank.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.url

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("webhooks:list")

    def subscribes_to(self, event_type: str) -> bool:
        return not self.event_types or event_type in self.event_types


class WebhookDelivery(models.Model):
    """Log of one attempted delivery of an event to an endpoint."""

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} → {self.endpoint.url}"
