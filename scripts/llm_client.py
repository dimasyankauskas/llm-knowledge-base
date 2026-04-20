"""LLM Knowledge Base v2 — LLM Client

Minimal wrapper for Anthropic Claude or Ollama (OpenAI-compatible API).
Set OLLAMA_BASE_URL to use Ollama instead of Anthropic.

Usage:
    from llm_client import completion, completion_with_retry

For Ollama:
    OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=qwen3.5:agentic \\
        python scripts/cli.py ingest --auto sources/my-file.md
"""

from __future__ import annotations

import os
import time
from typing import Optional

# Anthropic SDK — install with: pip install anthropic
try:
    from anthropic import Anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    Anthropic = None  # type: ignore
    _HAS_ANTHROPIC = False

# OpenAI SDK (for Ollama/OpenAI-compatible APIs)
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:
    OpenAI = None  # type: ignore
    _HAS_OPENAI = False


# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-7-20250608"
DEFAULT_OLLAMA_MODEL = "qwen3.5:agentic"
DEFAULT_TEMPERATURE = 0.4
DEFAULT_TIMEOUT_SECONDS = 120
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0


# ── Provider Detection ────────────────────────────────────────────────────────


def _provider() -> str:
    """Return 'ollama' if OLLAMA_BASE_URL or ANTHROPIC_BASE_URL is set, else 'anthropic'."""
    if os.environ.get("OLLAMA_BASE_URL"):
        return "ollama"
    if os.environ.get("ANTHROPIC_BASE_URL"):
        return "ollama"
    return "anthropic"


# ── Anthropic Client ──────────────────────────────────────────────────────────


def _get_anthropic_client() -> Anthropic:
    """Create a singleton Anthropic client."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it in your environment or .env file."
        )
    return Anthropic(api_key=api_key)


# ── OpenAI-compatible Client (Ollama) ───────────────────────────────────────


def _get_ollama_client() -> OpenAI:
    """Create a singleton OpenAI-compatible client for Ollama."""
    if not _HAS_OPENAI:
        raise RuntimeError(
            "OpenAI Python package not installed. Run: pip install openai"
        )
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return OpenAI(
        api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
        base_url=f"{base_url}/v1",
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )


# ── Core Completion ─────────────────────────────────────────────────────────


def completion(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = 4096,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Call an LLM for a text completion.

    Uses Ollama (OpenAI-compatible) if OLLAMA_BASE_URL is set,
    otherwise falls back to Anthropic Claude.

    Args:
        prompt: User message content.
        system_prompt: Optional system prompt.
        model: Model ID. Defaults to qwen3.5:agentic (Ollama) or
               claude-sonnet-4-7-20250608 (Anthropic).
        temperature: Sampling temperature (0.0–1.0).
        max_tokens: Maximum tokens in response.
        timeout: Request timeout in seconds.

    Returns:
        The full text content of the response.

    Raises:
        RuntimeError: If no API key / endpoint configured or SDK not installed.
    """
    provider = _provider()

    if provider == "ollama":
        if not _HAS_OPENAI:
            raise RuntimeError(
                "OpenAI Python package not installed. Run: pip install openai"
            )
        client = _get_ollama_client()
        model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL

        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=temperature,
        )
        msg = response.choices[0].message
        content = msg.content or ""
        if not content and msg.model_extra:
            content = msg.model_extra.get("reasoning", "")
        return content

    else:
        if not _HAS_ANTHROPIC:
            raise RuntimeError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )
        client = _get_anthropic_client()
        model = model or DEFAULT_ANTHROPIC_MODEL
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt if system_prompt else None,
            messages=messages,  # type: ignore
            timeout=timeout,
        )
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "\n\n".join(text_parts)


def completion_with_retry(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = 4096,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
    base_backoff: float = BASE_BACKOFF_SECONDS,
) -> str:
    """Call completion with exponential backoff on retriable errors.

    Retries on:
    - 429 (rate limit)
    - 500 (internal server error)
    - 529 (service unavailable)

    Does not retry on 400 (bad request) or 401 (auth error) — those are fatal.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return completion(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            last_error = e
            status_code = getattr(e, "status_code", None)

            # Fatal errors — don't retry
            if status_code in (400, 401, 403, 404):
                raise

            # Retriable errors
            if status_code in (429, 500, 502, 503, 529) and attempt < max_retries:
                backoff = base_backoff * (2 ** attempt)
                import random
                jitter = random.uniform(0, backoff * 0.1)
                sleep_time = backoff + jitter
                if attempt < max_retries - 1:
                    time.sleep(sleep_time)
                continue

            # Other errors — don't retry
            raise

    if last_error:
        raise last_error
    raise RuntimeError("completion_with_retry: exhausted retries with no error")


# ── Token Counting ────────────────────────────────────────────────────────────


def count_tokens(text: str, model: str = DEFAULT_ANTHROPIC_MODEL) -> int:
    """Rough token estimate.

    Uses Anthropic's count method if available, otherwise a
    rough heuristic (~4 chars per token for English).
    """
    if _HAS_ANTHROPIC and _provider() == "anthropic":
        try:
            client = _get_anthropic_client()
            return client.count_tokens(text)  # type: ignore
        except Exception:
            pass
    return len(text) // 4


# ── CLI (for testing) ────────────────────────────────────────────────────────


def main() -> None:
    """CLI: python scripts/llm_client.py [--prompt PROMPT] [--model MODEL]"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM Client test")
    parser.add_argument("--prompt", default="What is 2+2? Answer in one word.", help="Test prompt")
    parser.add_argument("--model", default=None, help="Model ID (uses OLLAMA_MODEL or default)")
    parser.add_argument("--system", default=None, help="System prompt")

    args = parser.parse_args()

    try:
        result = completion_with_retry(
            prompt=args.prompt,
            system_prompt=args.system,
            model=args.model,
        )
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=__import__("sys").stderr)
        raise


if __name__ == "__main__":
    main()
