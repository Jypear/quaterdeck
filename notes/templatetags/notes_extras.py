from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

from notes.markdown import render_markdown

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text: str) -> str:
    return mark_safe(render_markdown(text or ""))
