"""Shared markdown-to-HTML rendering for note bodies and AI previews.

`escape=True` is mistune's default and keeps raw HTML in note content (typed
by the user, or pulled in via AI web search) as literal text rather than
executable markup.
"""

from __future__ import annotations

import mistune

_renderer = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "table", "url", "task_lists"],
)


def render_markdown(text: str) -> str:
    """Render `text` as sanitised markdown HTML."""
    return _renderer(text)
