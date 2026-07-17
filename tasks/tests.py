"""Unit tests for the tasks app's done-toggle view."""

from __future__ import annotations

from datetime import date

from django.test import TestCase
from django.urls import reverse

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
