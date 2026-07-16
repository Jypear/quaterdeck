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
  {{"type": "link_project", "project_id": int}},
  {{"type": "link_pot", "pot_id": int}},
  {{"type": "link_one_off", "one_off_id": int}},
  {{"type": "create_project", "name": str, "description": str}}
]}}

Only suggest "link_project" using one of these existing project IDs: {projects}
Only suggest "link_pot" using one of these existing pot IDs: {pots}
Only suggest "link_one_off" using one of these existing one-off payment IDs: {one_offs}
Suggest "create_project" only if the note describes a new body of work that \
doesn't fit any existing project above.
If nothing is worth suggesting, return {{"actions": []}}.

Note title: {title}
Note body:
{body}
"""

_ENRICH_PROMPT_TEMPLATE = """\
You are helping someone who jots down rough, unstructured notes. Read the \
note below and rewrite it: answer any open questions it raises, research \
and fill in concrete details it asks for (e.g. price out materials, look up \
facts), tidy up the structure, and expand shorthand into full sentences \
where useful. Keep their intent and any decisions they've already made — \
don't invent facts you can't support.

Respond with ONLY the rewritten note body as plain markdown text. No \
preamble, no explanation of what you changed, no code fences.

Note title: {title}
Note body:
{body}
"""


def build_prompt(note: Note, projects: Any, pots: Any = (), one_offs: Any = ()) -> str:
    """Build the suggestions prompt for `note`, listing candidates to link it to."""
    project_list = ", ".join(f"{p.pk}={p.name}" for p in projects) or "(none)"
    pot_list = ", ".join(f"{p.pk}={p.name}" for p in pots) or "(none)"
    one_off_list = ", ".join(f"{o.pk}={o.name}" for o in one_offs) or "(none)"
    return _PROMPT_TEMPLATE.format(
        projects=project_list,
        pots=pot_list,
        one_offs=one_off_list,
        title=note.title,
        body=note.body,
    )


def build_enrich_prompt(note: Note) -> str:
    """Build the enrichment prompt asking the model to rewrite `note`'s body."""
    return _ENRICH_PROMPT_TEMPLATE.format(title=note.title, body=note.body)


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

        assert parse_actions('{"actions": [{"type": "link_pot", "pot_id": 1}]}') == [{"type": "link_pot", "pot_id": 1}]
        assert build_enrich_prompt(_FakeNote("Trip", "Book flights")).endswith("Book flights\n")

    class _FakeNote:
        def __init__(self, title: str, body: str) -> None:
            self.title = title
            self.body = body

    demo()
