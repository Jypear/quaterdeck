"""Prompt-building and response-parsing for on-demand note enrichment.

Kept separate from notes/views.py so the parsing logic (the part most likely
to break against a real model's output) has its own runnable self-check.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from notes.models import Note

_PROMPT_TEMPLATE = """\
You are helping organise a personal notes app. Read the note below and \
suggest follow-up actions. Respond with JSON ONLY (no prose, no markdown \
fences), matching this shape:

{{"actions": [
  {{"type": "create_task", "title": str, "priority": "low"|"medium"|"high", \
"due_date": "YYYY-MM-DD" or null, "budget_amount": number or null}},
  {{"type": "link_project", "project_id": int}}
]}}

Only suggest "link_project" using one of these existing project IDs: {projects}
If nothing is worth suggesting, return {{"actions": []}}.

Note title: {title}
Note body:
{body}
"""


def build_prompt(note: Note, projects: Any) -> str:
    """Build the enrichment prompt for `note`, listing `projects` as link targets."""
    project_list = ", ".join(f"{p.pk}={p.name}" for p in projects) or "(none)"
    return _PROMPT_TEMPLATE.format(projects=project_list, title=note.title, body=note.body)


def parse_actions(text: str) -> list[dict[str, Any]]:
    """Extract the `actions` list from a model response.

    Tolerates markdown fences or stray prose around the JSON object. Returns
    an empty list if no valid JSON object with an `actions` list is found.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return []
    actions = data.get("actions") if isinstance(data, dict) else None
    return actions if isinstance(actions, list) else []


if __name__ == "__main__":

    def demo() -> None:
        fenced = '```json\n{"actions": [{"type": "link_project", "project_id": 3}]}\n```'
        assert parse_actions(fenced) == [{"type": "link_project", "project_id": 3}]

        assert parse_actions("not json at all") == []
        assert parse_actions("") == []
        assert parse_actions('{"actions": "nope"}') == []

    demo()
