"""Provider registration and API-key management.

Phase 3. Nodes ask for a model by persona and never touch a provider SDK,
which is what lets Phase 7 add a provider at runtime without editing node
code.

Note on keys: settings reads backend/.env into the Settings object, but the
LangChain provider classes look in os.environ. Passing the key explicitly
here is what bridges that, rather than relying on the process environment
happening to be populated.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.llm.personas import Persona, get_persona

# provider key -> (settings attribute holding the API key, init_chat_model id)
PROVIDERS: dict[str, tuple[str, str]] = {
    "openrouter": ("OPENROUTER_API_KEY", "openrouter"),
    "openai": ("OPENAI_API_KEY", "openai"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek"),
}

DEFAULT_PROVIDER = "openrouter"


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider is requested but its API key is absent."""


def available_providers() -> list[str]:
    """Providers that currently have a key — what the frontend should offer."""
    return [p for p, (attr, _) in PROVIDERS.items() if getattr(settings, attr, None)]


def get_model(provider: str = DEFAULT_PROVIDER, model: str | None = None,
              **kwargs: Any):
    """Return a configured LangChain chat model."""
    if provider not in PROVIDERS:
        raise ProviderNotConfigured(
            f"Unknown provider '{provider}'; known: {sorted(PROVIDERS)}")

    key_attr, provider_id = PROVIDERS[provider]
    api_key = getattr(settings, key_attr, None)
    if not api_key:
        raise ProviderNotConfigured(f"{key_attr} is not set in backend/.env")

    from langchain.chat_models import init_chat_model

    if provider == "openrouter":
        kwargs.setdefault("openrouter_api_key", api_key)
        model = model or settings.OPENROUTER_MODEL
    else:
        kwargs.setdefault("api_key", api_key)

    return init_chat_model(model, model_provider=provider_id, **kwargs)


def get_model_for_persona(persona_key: str | None = None,
                          provider: str = DEFAULT_PROVIDER) -> tuple[Persona, Any]:
    """Resolve a persona and the model bound to it. Used by PersonaSelector."""
    persona = get_persona(persona_key)
    return persona, get_model(provider)
