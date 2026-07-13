"""Tests for note CRUD and on-demand AI enrichment."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from ai.providers import BaseAIProvider
from notes.ai import parse_actions
from notes.models import Note
from projects.models import Project
from tasks.models import Task


class NoteCrudTests(TestCase):
    def test_create_edit_delete_round_trip(self) -> None:
        add_response = self.client.post(reverse("notes:note_add"), {"title": "Idea", "body": "Do a thing"})
        note = Note.objects.get(title="Idea")
        assert add_response.status_code == 302
        assert add_response["Location"] == note.get_absolute_url()

        self.client.post(reverse("notes:note_edit", args=[note.pk]), {"title": "Idea v2", "body": "Do a thing"})
        note.refresh_from_db()
        assert note.title == "Idea v2"

        self.client.post(reverse("notes:note_delete", args=[note.pk]))
        assert not Note.objects.filter(pk=note.pk).exists()


class _FakeProvider(BaseAIProvider):
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        return self._reply


class EnrichNoteTests(TestCase):
    def setUp(self) -> None:
        self.note = Note.objects.create(title="Trip planning", body="Book flights, budget £500")
        self.project = Project.objects.create(name="Holiday")

    def test_unconfigured_provider_shows_setup_prompt(self) -> None:
        response = self.client.post(reverse("notes:note_enrich", args=[self.note.pk]))
        assert b"Set one up in Settings" in response.content

    def test_configured_provider_renders_suggested_actions(self) -> None:
        reply = (
            '{"actions": [{"type": "create_task", "title": "Book flights", '
            '"priority": "high", "due_date": null, "budget_amount": 500}]}'
        )
        with patch("notes.views.get_provider", return_value=_FakeProvider(reply)):
            response = self.client.post(reverse("notes:note_enrich", args=[self.note.pk]))
        assert b"Book flights" in response.content

    def test_apply_create_task_action_creates_linked_task(self) -> None:
        self.note.linked_project = self.project
        self.note.save(update_fields=["linked_project"])

        self.client.post(
            reverse("notes:note_apply_action", args=[self.note.pk]),
            {"type": "create_task", "title": "Book flights", "priority": "high"},
        )

        task = Task.objects.get(title="Book flights")
        assert task.priority == Task.Priority.HIGH
        assert task.linked_project == self.project

    def test_apply_link_project_action_links_note(self) -> None:
        self.client.post(
            reverse("notes:note_apply_action", args=[self.note.pk]),
            {"type": "link_project", "project_id": self.project.pk},
        )
        self.note.refresh_from_db()
        assert self.note.linked_project == self.project


class ParseActionsTests(TestCase):
    def test_extracts_actions_from_fenced_json(self) -> None:
        text = '```json\n{"actions": [{"type": "link_project", "project_id": 3}]}\n```'
        assert parse_actions(text) == [{"type": "link_project", "project_id": 3}]

    def test_returns_empty_list_for_garbage(self) -> None:
        assert parse_actions("not json") == []
