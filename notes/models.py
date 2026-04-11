"""Notes domain model."""

from django.db import models


class Note(models.Model):
    title = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    linked_project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title
