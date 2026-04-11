"""Provider-agnostic AI abstraction layer.

Usage:
    from ai.providers import get_provider
    provider = get_provider()          # reads Settings
    reply = provider.complete(prompt)  # returns str
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAIProvider(ABC):
    """Minimal interface all providers must implement."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send *prompt* and return the model's text response."""


class NullProvider(BaseAIProvider):
    """Returned when no AI provider is configured."""

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        return ""


class AnthropicProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        import openai  # type: ignore[import-untyped]

        client = openai.OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class OllamaProvider(BaseAIProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url

    def complete(self, prompt: str) -> str:
        import json
        import urllib.request

        payload = json.dumps({"model": self._model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data.get("response", "")


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
