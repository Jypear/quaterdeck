"""Unit tests for the tasks app's done-toggle view."""

from __future__ import annotations

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
