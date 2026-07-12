"""Projects domain model."""

from django.db import models
from django.urls import reverse


class Project(models.Model):
    """A container linking tasks, notes, pots, and calendar events."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("projects:detail", args=[self.pk])
