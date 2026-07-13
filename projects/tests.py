"""Unit tests for the project budget view (linked-pot progress vs. project cost)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from budget.models import Pot, PotEntry
from budget.services import active_period
from core.models import Settings
from projects.models import Project


class ProjectBudgetViewTests(TestCase):
    def setUp(self) -> None:
        self.project = Project.objects.create(name="Kitchen reno", budget=Decimal("1000"))
        self.pot = Pot.objects.create(
            name="Reno fund",
            target_amount=Decimal("1000"),
            target_date=date(2027, 1, 1),
            monthly_target=Decimal("100"),
            linked_project=self.project,
        )
        settings = Settings.get()
        self.period = active_period(settings.budget_mode, settings.budget_start_day)
        PotEntry.objects.create(pot=self.pot, period_start=self.period.start, actual_amount=Decimal("250"))

    def test_total_saved_and_pct_reflect_linked_pot_entries(self) -> None:
        response = self.client.get(reverse("projects:detail", args=[self.project.pk]))
        assert response.status_code == 200
        assert response.context["total_saved"] == Decimal("250")
        assert response.context["budget_pct"] == 25

    def test_no_budget_set_gives_no_percentage(self) -> None:
        project = Project.objects.create(name="No cost project")
        response = self.client.get(reverse("projects:detail", args=[project.pk]))
        assert response.context["budget_pct"] is None
        assert response.context["pot_rows"] == []

    def test_add_pot_link_preselects_project_and_next(self) -> None:
        url = reverse("budget:pot_add")
        response = self.client.post(
            f"{url}?linked_project={self.project.pk}&next=/projects/{self.project.pk}/",
            {
                "name": "Extra fund",
                "target_amount": "500",
                "target_date": "2027-01-01",
                "monthly_target": "50",
                "linked_project": self.project.pk,
            },
        )
        assert response.status_code == 302
        assert response.url == f"/projects/{self.project.pk}/"
        assert Pot.objects.filter(name="Extra fund", linked_project=self.project).exists()
