"""Provider-agnostic AI abstraction layer.

Usage:
    from ai.providers import get_provider
    provider = get_provider()          # reads Settings
    reply = provider.complete(prompt)  # returns str
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


class BaseAIProvider(ABC):
    """Minimal interface all providers must implement."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str = "") -> str:
        """Send *prompt* and return the model's text response.

        `system` is the user's configured Settings.ai_system_prompt (e.g.
        location/currency context) sent as a system-level instruction.
        """

    def stream(self, prompt: str, *, web_search: bool = False, system: str = "") -> Iterator[str]:  # noqa: ARG002
        """Yield the response incrementally. `web_search` is a hint providers may ignore.

        Default fallback for providers without real token streaming: yields the
        whole `complete()` result as one chunk.
        """
        yield self.complete(prompt, system=system)


class NullProvider(BaseAIProvider):
    """Returned when no AI provider is configured."""

    def complete(self, prompt: str, *, system: str = "") -> str:  # noqa: ARG002
        return ""


class AnthropicProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str, *, system: str = "") -> str:
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def stream(self, prompt: str, *, web_search: bool = False, system: str = "") -> Iterator[str]:
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=self._api_key)
        tools = [{"type": "web_search_20250305", "name": "web_search"}] if web_search else []
        with client.messages.stream(
            model=self._model,
            max_tokens=4096,
            system=system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
        ) as s:
            yield from s.text_stream


class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str, *, system: str = "") -> str:
        import openai  # type: ignore[import-untyped]

        client = openai.OpenAI(api_key=self._api_key)
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(model=self._model, messages=messages)
        return response.choices[0].message.content or ""

    def stream(self, prompt: str, *, web_search: bool = False, system: str = "") -> Iterator[str]:
        import openai  # type: ignore[import-untyped]

        client = openai.OpenAI(api_key=self._api_key)
        tools = [{"type": "web_search"}] if web_search else []
        with client.responses.stream(model=self._model, input=prompt, instructions=system or None, tools=tools) as s:
            for event in s:
                if event.type == "response.output_text.delta":
                    yield event.delta


class OllamaProvider(BaseAIProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url

    def complete(self, prompt: str, *, system: str = "") -> str:
        import json
        import urllib.request

        payload = json.dumps({"model": self._model, "prompt": prompt, "system": system, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data.get("response", "")

    def stream(self, prompt: str, *, web_search: bool = False, system: str = "") -> Iterator[str]:  # noqa: ARG002
        import json
        import urllib.request

        # ponytail: web_search is unsupported by Ollama and silently ignored here.
        payload = json.dumps({"model": self._model, "prompt": prompt, "system": system, "stream": True}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("response"):
                    yield chunk["response"]


def get_provider() -> BaseAIProvider:
    """Return the configured AI provider, or NullProvider if none is set."""
    from core.models import Settings

    s = Settings.get()

    match s.ai_provider:
        case "anthropic":
            return AnthropicProvider(api_key=s.ai_api_key, model=s.ai_model)
        case "openai":
            return OpenAIProvider(api_key=s.ai_api_key, model=s.ai_model)
        case "ollama":
            return OllamaProvider(model=s.ai_model)
        case _:
            return NullProvider()
