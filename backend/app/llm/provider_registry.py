"""Provider registration.

OpenRouter backs every model by name, except the free GMI Cloud MiniMax
models, which are routed to the GMI endpoint. A node still just asks for a
model id and never touches a provider SDK.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings

# Free models served by GMI Cloud (OpenAI-compatible endpoint).
GMI_MODELS = {"MiniMaxAI/MiniMax-M2.7", "MiniMaxAI/MiniMax-M3"}


class ProviderNotConfigured(RuntimeError):
    """Raised when a requested provider has no API key set in backend/.env."""


def get_model(
    model: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
):
    """Return a LangChain chat model for the given model id.

    GMI MiniMax ids go to GMI Cloud; everything else goes to OpenRouter.
    """
    model = model or settings.OPENROUTER_MODEL

    from langchain.chat_models import init_chat_model

    if model in GMI_MODELS:
        if not settings.GMI_API_KEY:
            raise ProviderNotConfigured("GMI_API_KEY is not set in backend/.env")
        return init_chat_model(
            model,
            model_provider="openai",
            api_key=settings.GMI_API_KEY,
            base_url=base_url or settings.GMI_BASE_URL,
            **kwargs,
        )

    if not settings.OPENROUTER_API_KEY:
        raise ProviderNotConfigured("OPENROUTER_API_KEY is not set in backend/.env")
    return init_chat_model(
        model,
        model_provider="openrouter",
        openrouter_api_key=settings.OPENROUTER_API_KEY,
        base_url=base_url or settings.OPENROUTER_BASE_URL,
        **kwargs,
    )
