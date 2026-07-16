"""Tests for note CRUD and the two on-demand AI features (suggest, enrich)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from ai.providers import BaseAIProvider
from budget.models import Account, OneOffOutgoing, Pot
from core.models import Settings
from notes.ai import parse_actions
from notes.markdown import render_markdown
from notes.models import Note
from projects.models import Project
from tasks.models import Task

if TYPE_CHECKING:
    from collections.abc import Iterator


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


class NoteMarkdownRenderingTests(TestCase):
    def test_renders_markdown_formatting_to_html(self) -> None:
        html = render_markdown("**bold** and a list:\n\n- one\n- two")
        assert "<strong>bold</strong>" in html
        assert "<li>one</li>" in html

    def test_escapes_raw_html_instead_of_executing_it(self) -> None:
        html = render_markdown("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_detail_page_renders_note_body_as_markdown(self) -> None:
        note = Note.objects.create(title="Formatted", body="**bold text**")
        response = self.client.get(note.get_absolute_url())
        self.assertContains(response, "<strong>bold text</strong>")

    def test_render_markdown_preview_endpoint_returns_html(self) -> None:
        response = self.client.post(reverse("notes:render_markdown"), {"text": "**bold**"})
        assert b"<strong>bold</strong>" in response.content


class _FakeProvider(BaseAIProvider):
    def __init__(self, reply: str = "", stream_chunks: list[str] | None = None) -> None:
        self._reply = reply
        self._stream_chunks = stream_chunks or []
        self.last_system: str | None = None

    def complete(self, prompt: str, *, system: str = "") -> str:  # noqa: ARG002
        self.last_system = system
        return self._reply

    def stream(self, prompt: str, *, web_search: bool = False, system: str = "") -> Iterator[str]:  # noqa: ARG002
        self.last_system = system
        yield from self._stream_chunks


class SuggestNoteTests(TestCase):
    def setUp(self) -> None:
        self.note = Note.objects.create(title="Trip planning", body="Book flights, budget £500")
        self.project = Project.objects.create(name="Holiday")
        account = Account.objects.create(name="Main")
        self.pot = Pot.objects.create(
            name="Holiday fund", target_amount=1000, target_date="2026-12-31", monthly_target=100
        )
        self.one_off = OneOffOutgoing.objects.create(name="Flights", amount=500, due_date="2026-09-01", account=account)

    def test_unconfigured_provider_shows_setup_prompt(self) -> None:
        response = self.client.post(reverse("notes:note_suggest", args=[self.note.pk]))
        assert b"Set one up in Settings" in response.content

    def test_configured_provider_renders_suggested_actions(self) -> None:
        reply = (
            '{"actions": [{"type": "create_task", "title": "Book flights", '
            '"priority": "high", "due_date": null, "budget_amount": 500}]}'
        )
        with patch("notes.views.get_provider", return_value=_FakeProvider(reply=reply)):
            response = self.client.post(reverse("notes:note_suggest", args=[self.note.pk]))
        assert b"Book flights" in response.content

    def test_passes_settings_system_prompt_to_provider(self) -> None:
        Settings.get()
        Settings.objects.update(ai_system_prompt="User is based in the UK; use GBP and UK retailers.")
        fake = _FakeProvider(reply='{"actions": []}')
        with patch("notes.views.get_provider", return_value=fake):
            self.client.post(reverse("notes:note_suggest", args=[self.note.pk]))
        assert fake.last_system == "User is based in the UK; use GBP and UK retailers."

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

    def test_apply_link_pot_action_links_note(self) -> None:
        self.client.post(
            reverse("notes:note_apply_action", args=[self.note.pk]),
            {"type": "link_pot", "pot_id": self.pot.pk},
        )
        self.note.refresh_from_db()
        assert self.note.linked_pot == self.pot

    def test_apply_link_one_off_action_links_note(self) -> None:
        self.client.post(
            reverse("notes:note_apply_action", args=[self.note.pk]),
            {"type": "link_one_off", "one_off_id": self.one_off.pk},
        )
        self.note.refresh_from_db()
        assert self.note.linked_one_off == self.one_off

    def test_apply_create_project_action_creates_and_links_project(self) -> None:
        self.client.post(
            reverse("notes:note_apply_action", args=[self.note.pk]),
            {"type": "create_project", "name": "New Kitchen", "description": "Renovate the kitchen"},
        )
        self.note.refresh_from_db()
        assert self.note.linked_project is not None
        assert self.note.linked_project.name == "New Kitchen"


class EnrichNoteTests(TestCase):
    def setUp(self) -> None:
        self.note = Note.objects.create(title="Trip planning", body="Book flights, budget £500")

    def test_unconfigured_provider_streams_setup_prompt(self) -> None:
        response = self.client.post(reverse("notes:note_enrich", args=[self.note.pk]))
        content = b"".join(response.streaming_content)
        assert b"Set one up in Settings" in content

    def test_configured_provider_streams_chunks(self) -> None:
        fake = _FakeProvider(stream_chunks=["Booked ", "flights ", "for £500."])
        with patch("notes.views.get_provider", return_value=fake):
            response = self.client.post(reverse("notes:note_enrich", args=[self.note.pk]))
        content = b"".join(response.streaming_content)
        assert content == b"Booked flights for \xc2\xa3500."

    def test_passes_settings_system_prompt_to_provider(self) -> None:
        Settings.get()
        Settings.objects.update(ai_system_prompt="User is based in the UK; use GBP and UK retailers.")
        fake = _FakeProvider(stream_chunks=["ok"])
        with patch("notes.views.get_provider", return_value=fake):
            response = self.client.post(reverse("notes:note_enrich", args=[self.note.pk]))
            b"".join(response.streaming_content)  # force generator to run
        assert fake.last_system == "User is based in the UK; use GBP and UK retailers."

    def test_enrich_apply_replaces_note_body(self) -> None:
        self.client.post(
            reverse("notes:note_enrich_apply", args=[self.note.pk]),
            {"body": "Rewritten and researched note body."},
        )
        self.note.refresh_from_db()
        assert self.note.body == "Rewritten and researched note body."


class ParseActionsTests(TestCase):
    def test_extracts_actions_from_fenced_json(self) -> None:
        text = '```json\n{"actions": [{"type": "link_project", "project_id": 3}]}\n```'
        assert parse_actions(text) == [{"type": "link_project", "project_id": 3}]

    def test_returns_empty_list_for_garbage(self) -> None:
        assert parse_actions("not json") == []
