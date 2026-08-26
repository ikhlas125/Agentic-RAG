"""Provider registration — OpenRouter is the single provider; a single API
key backs every model, so a node picks a model by name rather than by
provider.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings


class ProviderNotConfigured(RuntimeError):
    """Raised when OPENROUTER_API_KEY is absent."""


def get_model(
    model: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
):
    """Return a LangChain chat model for the given OpenRouter model id."""
    if not settings.OPENROUTER_API_KEY:
        raise ProviderNotConfigured("OPENROUTER_API_KEY is not set in backend/.env")

    from langchain.chat_models import init_chat_model

    return init_chat_model(
        model or settings.OPENROUTER_MODEL,
        model_provider="openrouter",
        openrouter_api_key=settings.OPENROUTER_API_KEY,
        base_url=base_url or settings.OPENROUTER_BASE_URL,
        **kwargs,
    )
