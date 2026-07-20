"""Shared helpers for filterable/sortable list-table views (tasks, projects, notes).

# ponytail: hand-rolled GET-param parsing, matching budget/views.py's existing
# approach — no django-filter dependency for this much logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest, QueryDict


def is_partial(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def apply_sort(
    params: QueryDict,
    queryset: QuerySet,
    allowed: dict[str, str],
    default: str,
) -> tuple[QuerySet, str, str]:
    """Order `queryset` by `params["sort"]`/`params["dir"]` (validated against `allowed`).

    `params` is a `request.GET` or `request.POST` QueryDict — passing the raw
    dict (rather than the request) lets POST views like `toggle_done` reorder
    with whatever filters were `hx-include`d, same as a GET listing.
    `allowed` maps a public column key (used in the URL and template) to the
    ORM field/lookup to order by. Falls back to `default` (a key in `allowed`)
    for a missing or invalid `sort`. Returns (ordered_queryset, sort_col, sort_dir).
    """
    col = params.get("sort")
    if col not in allowed:
        col = default
    direction = "desc" if params.get("dir") == "desc" else "asc"
    field = allowed[col]
    return queryset.order_by(f"-{field}" if direction == "desc" else field), col, direction
