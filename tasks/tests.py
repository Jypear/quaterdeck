"""Unit tests for the tasks app's done-toggle view and the filterable/sortable table."""

from __future__ import annotations

from datetime import date

from django.test import TestCase
from django.urls import reverse

from projects.models import Project
from tasks.models import Task


class ToggleDoneTests(TestCase):
    def test_toggle_flips_status_and_moves_between_lists(self) -> None:
        task = Task.objects.create(title="Write plan")
        assert task.status == Task.Status.TODO

        self.client.post(reverse("tasks:task_toggle_done", args=[task.pk]))
        task.refresh_from_db()
        assert task.status == Task.Status.DONE

        self.client.post(reverse("tasks:task_toggle_done", args=[task.pk]))
        task.refresh_from_db()
        assert task.status == Task.Status.TODO

    def test_toggle_preserves_active_filters_in_rerendered_table(self) -> None:
        """The toggle form `hx-include`s the filter form, so the re-rendered table
        should only contain rows matching the filters that were active."""
        matching = Task.objects.create(title="Buy milk", priority=Task.Priority.HIGH)
        other = Task.objects.create(title="Write report", priority=Task.Priority.LOW)

        response = self.client.post(
            reverse("tasks:task_toggle_done", args=[matching.pk]),
            {"priority": Task.Priority.HIGH},
        )
        content = response.content.decode()
        assert matching.title in content
        assert other.title not in content


class TaskTableFilterTests(TestCase):
    def setUp(self) -> None:
        self.project = Project.objects.create(name="Kitchen reno")
        self.task_a = Task.objects.create(
            title="Buy tiles", priority=Task.Priority.HIGH, status=Task.Status.TODO, linked_project=self.project
        )
        self.task_b = Task.objects.create(title="Call plumber", priority=Task.Priority.LOW, status=Task.Status.DONE)

    def test_search_filters_by_title(self) -> None:
        response = self.client.get(reverse("tasks:list"), {"q": "tiles"})
        tasks = list(response.context["tasks"])
        assert tasks == [self.task_a]

    def test_status_filter_narrows_results(self) -> None:
        response = self.client.get(reverse("tasks:list"), {"status": Task.Status.DONE})
        tasks = list(response.context["tasks"])
        assert tasks == [self.task_b]

    def test_project_filter_narrows_results(self) -> None:
        response = self.client.get(reverse("tasks:list"), {"linked_project": self.project.pk})
        tasks = list(response.context["tasks"])
        assert tasks == [self.task_a]

    def test_sort_by_title_descending(self) -> None:
        response = self.client.get(reverse("tasks:list"), {"sort": "title", "dir": "desc"})
        titles = [task.title for task in response.context["tasks"]]
        assert titles == ["Call plumber", "Buy tiles"]

    def test_htmx_request_returns_table_partial_only(self) -> None:
        response = self.client.get(reverse("tasks:list"), HTTP_HX_REQUEST="true")
        content = response.content.decode()
        assert "<html" not in content
        assert self.task_a.title in content


class TaskCreateDatePrefillTests(TestCase):
    """Regression: the calendar's "+" links pass `?date=` to pre-fill due_date."""

    def test_valid_date_prefills_due_date(self) -> None:
        response = self.client.get(reverse("tasks:task_add"), {"date": "2026-07-15"})
        assert response.context["form"].initial["due_date"] == date(2026, 7, 15)
        # The rendered <input type="date"> needs an ISO value or the browser
        # silently blanks it, regardless of locale (en-gb formats DD/MM/YYYY).
        assert 'value="2026-07-15"' in response.content.decode()

    def test_missing_or_invalid_date_leaves_it_unset(self) -> None:
        response = self.client.get(reverse("tasks:task_add"))
        assert "due_date" not in response.context["form"].initial

        response = self.client.get(reverse("tasks:task_add"), {"date": "not-a-date"})
        assert "due_date" not in response.context["form"].initial
