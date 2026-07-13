"""Tests for webhook signing, outbound dispatch, signal wiring, and the inbound receiver."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import Settings
from tasks.models import Task
from webhooks.models import WebhookEndpoint
from webhooks.services import dispatch_event, sign, verify


class _ImmediateThread:
    """Stand-in for threading.Thread that runs its target synchronously.

    Keeps dispatch_event's threaded delivery deterministic in tests.
    """

    def __init__(self, target: Any = None, args: tuple = (), daemon: bool = False) -> None:  # noqa: ARG002
        self._target = target
        self._args = args

    def start(self) -> None:
        self._target(*self._args)


class SignVerifyTests(TestCase):
    def test_verify_accepts_matching_signature(self) -> None:
        body = b'{"a": 1}'
        header = sign("shh", body)
        assert verify("shh", body, header)

    def test_verify_rejects_tampered_body(self) -> None:
        header = sign("shh", b'{"a": 1}')
        assert not verify("shh", b'{"a": 2}', header)

    def test_verify_rejects_wrong_secret(self) -> None:
        body = b'{"a": 1}'
        header = sign("shh", body)
        assert not verify("other", body, header)


class DispatchEventTests(TestCase):
    def setUp(self) -> None:
        self.subscribed = WebhookEndpoint.objects.create(url="http://a.example", event_types=["task.created"])
        self.unsubscribed = WebhookEndpoint.objects.create(url="http://b.example", event_types=["pot.created"])
        self.inactive = WebhookEndpoint.objects.create(url="http://c.example", event_types=[], is_active=False)
        self.catch_all = WebhookEndpoint.objects.create(url="http://d.example", event_types=[])

    def test_dispatches_only_to_active_subscribed_endpoints(self) -> None:
        with (
            patch("webhooks.services.threading.Thread", _ImmediateThread),
            patch("webhooks.services._deliver") as mock_deliver,
        ):
            dispatch_event("task.created", {"id": 1})

        called_endpoints = {call.args[0] for call in mock_deliver.call_args_list}
        assert called_endpoints == {self.subscribed, self.catch_all}


class TaskSignalTests(TestCase):
    def test_creating_a_task_dispatches_task_created(self) -> None:
        with patch("webhooks.signals.dispatch_event") as mock_dispatch:
            Task.objects.create(title="Do a thing")

        events = [call.args[0] for call in mock_dispatch.call_args_list]
        assert "task.created" in events

    def test_deleting_a_task_dispatches_task_deleted(self) -> None:
        task = Task.objects.create(title="Do a thing")
        with patch("webhooks.signals.dispatch_event") as mock_dispatch:
            task.delete()

        events = [call.args[0] for call in mock_dispatch.call_args_list]
        assert "task.deleted" in events


class InboundWebhookTests(TestCase):
    def setUp(self) -> None:
        self.settings = Settings.get()
        self.settings.webhook_inbound_secret = "topsecret"
        self.settings.save()

    def _post(self, body: bytes, signature: str) -> Any:
        return self.client.post(
            reverse("webhooks:inbound"),
            data=body,
            content_type="application/json",
            HTTP_X_QUATERDECK_SIGNATURE=signature,
        )

    def test_bad_signature_is_rejected(self) -> None:
        body = json.dumps({"type": "create_task", "title": "X"}).encode()
        response = self._post(body, "sha256=deadbeef")
        assert response.status_code == 401

    def test_valid_signature_creates_task(self) -> None:
        body = json.dumps({"type": "create_task", "title": "From webhook"}).encode()
        response = self._post(body, sign("topsecret", body))
        assert response.status_code == 201
        assert Task.objects.filter(title="From webhook").exists()

    def test_unknown_type_is_rejected(self) -> None:
        body = json.dumps({"type": "nope"}).encode()
        response = self._post(body, sign("topsecret", body))
        assert response.status_code == 400
