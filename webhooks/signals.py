"""Signal receivers that fire outbound webhook events on model changes.

Reuses the existing DRF serializers (api/serializers already exist per app)
so payload shape matches the REST API. Only a curated set of user-facing
models/events is wired — see webhooks/models.py::EVENT_CHOICES for the
catalog this must stay in sync with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models.signals import post_delete, post_save

from budget.models import OneOffOutgoing, Pot
from budget.serializers import OneOffOutgoingSerializer, PotSerializer
from notes.models import Note
from notes.serializers import NoteSerializer
from tasks.models import Task
from tasks.serializers import TaskSerializer
from webhooks.services import dispatch_event

if TYPE_CHECKING:
    from django.db.models import Model
    from rest_framework.serializers import ModelSerializer


def _watch(model: type[Model], serializer_class: type[ModelSerializer], prefix: str, events: set[str]) -> None:
    """Connect post_save/post_delete receivers that dispatch `prefix.<event>` for each event in `events`."""

    if "created" in events or "updated" in events:

        def on_save(sender: type[Model], instance: Model, created: bool, **kwargs: Any) -> None:  # noqa: ARG001
            event = "created" if created else "updated"
            if event in events:
                dispatch_event(f"{prefix}.{event}", serializer_class(instance).data)

        post_save.connect(on_save, sender=model, weak=False)

    if "deleted" in events:

        def on_delete(sender: type[Model], instance: Model, **kwargs: Any) -> None:  # noqa: ARG001
            dispatch_event(f"{prefix}.deleted", serializer_class(instance).data)

        post_delete.connect(on_delete, sender=model, weak=False)


_watch(Task, TaskSerializer, "task", {"created", "updated", "deleted"})
_watch(Pot, PotSerializer, "pot", {"created", "updated"})
_watch(Note, NoteSerializer, "note", {"created"})
_watch(OneOffOutgoing, OneOffOutgoingSerializer, "oneoff", {"created"})
