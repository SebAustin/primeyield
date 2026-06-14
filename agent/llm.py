"""Provider-agnostic chat LLM factory.

Lets the agent run on OpenAI or Anthropic without touching node code. The
provider is chosen by the ``LLM_PROVIDER`` env var (``openai`` | ``anthropic``);
if unset, it defaults to whichever API key is present (OpenAI takes precedence
when both are set). Model ids are overridable via ``OPENAI_MODEL`` /
``ANTHROPIC_MODEL``.

Both providers return a message whose ``.content`` is the response string, so
the calling nodes are identical regardless of provider.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Ensure .env is loaded even if this module is used before agent.config.
load_dotenv()

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"


def resolve_provider() -> str:
    """Return the active provider name, honoring LLM_PROVIDER then key presence."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider:
        return provider
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"


def make_chat_llm(*, max_tokens: int, temperature: float):
    """Build a LangChain chat model for the active provider."""
    provider = resolve_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (use 'openai' or 'anthropic')")
