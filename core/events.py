"""Calendar events: buckets dated rows from other apps onto calendar days.

Pure/read-only — no HTTP, no writes. Mirrors budget/services.py's style
(dataclasses in, dataclasses out, models imported and queried directly).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.urls import reverse

from budget.models import OneOffOutgoing, Pot
from tasks.models import Task

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date


@dataclass(frozen=True)
class CalEvent:
    label: str
    url: str
    css: str  # bootstrap badge class


_PRIORITY_CSS = {
    Task.Priority.HIGH: "bg-danger",
    Task.Priority.MEDIUM: "bg-warning text-dark",
    Task.Priority.LOW: "bg-secondary",
}


def month_events(start: date, end: date) -> dict[date, list[CalEvent]]:
    """Events keyed by date across the half-open [start, end) range."""
    events: dict[date, list[CalEvent]] = defaultdict(list)

    tasks: Iterable[Task] = Task.objects.filter(due_date__gte=start, due_date__lt=end)
    for task in tasks:
        events[task.due_date].append(
            CalEvent(task.title, reverse("tasks:task_edit", args=[task.pk]), _PRIORITY_CSS[task.priority])
        )

    one_offs: Iterable[OneOffOutgoing] = OneOffOutgoing.objects.filter(due_date__gte=start, due_date__lt=end)
    for one_off in one_offs:
        events[one_off.due_date].append(
            CalEvent(
                f"{one_off.name} £{one_off.amount}",
                reverse("budget:oneoff_edit", args=[one_off.pk]),
                "bg-danger",
            )
        )

    pots: Iterable[Pot] = Pot.objects.filter(target_date__gte=start, target_date__lt=end)
    for pot in pots:
        events[pot.target_date].append(
            CalEvent(f"{pot.name} target", reverse("budget:pot_edit", args=[pot.pk]), "bg-success")
        )

    return events
