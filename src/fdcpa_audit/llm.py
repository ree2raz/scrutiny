"""
LLM provider abstraction.

Supports Hugging Face Inference API (default), Anthropic, OpenAI, and OpenRouter
via a factory function. Each provider implements the same interface: take a
system prompt and user message, return a string response.

No streaming. No retries. No caching. This is a reference implementation.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()


class LLMClient(ABC):
    """Base interface for LLM providers."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send a system+user prompt pair and return the text response."""
        ...


class AnthropicClient(LLMClient):
    """Anthropic Claude via the official SDK.

    Override model with ANTHROPIC_MODEL environment variable.
    """

    def __init__(self, model: str | None = None):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get(
            "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
        )

    def complete(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


class OpenAIClient(LLMClient):
    """OpenAI API via the official SDK.

    Override model with OPENAI_MODEL environment variable.
    """

    def __init__(self, model: str | None = None):
        import openai

        self.client = openai.OpenAI()
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content


class OpenRouterClient(LLMClient):
    """OpenRouter API — unified access to many models.

    Set OPENROUTER_API_KEY and optionally OPENROUTER_MODEL.
    Default model is anthropic/claude-sonnet-4.
    """

    def __init__(self, model: str | None = None):
        import openai

        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        self.model = model or os.environ.get(
            "OPENROUTER_MODEL", "anthropic/claude-sonnet-4"
        )

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content


class HuggingFaceClient(LLMClient):
    """Hugging Face Serverless Inference API (OpenAI-compatible endpoint).

    Set HF_TOKEN (optional on HF Spaces where it's auto-injected).
    Default model is google/gemma-4-31B-it.
    Override with HF_MODEL env var.

    Note: gemma-4 is a 31B model. On the free HF Inference tier it can
    take 2–4 minutes to cold-start, causing 504 timeouts. The client
    below uses a 300-second timeout and retries once automatically.
    If you need faster responses, switch to anthropic/openai/openrouter.
    """

    def __init__(self, model: str | None = None):
        import openai

        token = os.environ.get("HF_TOKEN")
        self.client = openai.OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=token or "dummy",  # HF Spaces injects HF_TOKEN; dummy fails fast locally
            timeout=300,  # 5 min — gemma-4 can take 2–4 min to cold-start
            max_retries=2,
        )
        self.model = model or os.environ.get(
            "HF_MODEL", "google/gemma-4-31B-it"
        )

    def complete(self, system: str, user: str) -> str:
        import time

        last_exc = None
        for attempt in range(1, 3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=4096,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return response.choices[0].message.content
            except Exception as exc:
                last_exc = exc
                # Retry on 504 Gateway Timeout or 503 Service Unavailable
                err_str = str(exc).lower()
                if "504" in err_str or "503" in err_str or "timeout" in err_str:
                    if attempt < 2:
                        wait = 5 * attempt
                        print(f"[HF Inference] Attempt {attempt} failed ({exc}). Retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                raise
        # Should never reach here, but just in case
        raise last_exc or RuntimeError("HF Inference failed after retries")


# Provider registry. Add new providers here.
_PROVIDERS: dict[str, type[LLMClient]] = {
    "huggingface": HuggingFaceClient,
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "openrouter": OpenRouterClient,
}


def get_llm_client(provider: str | None = None) -> LLMClient:
    """Factory: return an LLM client for the given provider name.

    Resolution order:
    1. Explicit `provider` argument
    2. LLM_PROVIDER environment variable
    3. Default to "huggingface"

    Raises ValueError if the provider name is not recognized.
    """
    name = provider or os.environ.get("LLM_PROVIDER", "huggingface")
    name = name.lower().strip()

    if name not in _PROVIDERS:
        valid = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown LLM provider '{name}'. Valid providers: {valid}"
        )

    return _PROVIDERS[name]()
