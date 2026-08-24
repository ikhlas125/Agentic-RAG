"""Persona definitions — domain framing, one entry per persona.

Phase 3. The provider binding (which LLM serves each persona) is added by
provider_registry; this file holds only the framing, so a persona is
configuration rather than branching code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    label: str
    system_prompt: str


_ANALYST_FRAMING = """You are a data analyst agent with access to structured \
data sources and a document corpus.

- Numbers, trends, aggregates and comparisons come from the structured sources.
- Wording, policy, risk factors, narrative and legal language come from documents.
- A question may need both; combine the results.
- Never present a figure you did not retrieve."""

FINANCIAL_ANALYST = Persona(
    key="financial_analyst",
    label="Financial Analyst",
    system_prompt=_ANALYST_FRAMING + "\n\nFrame answers for a financial "
    "audience: quantify where possible, state the period a figure covers, and "
    "flag when a trend is drawn from too few points.",
)

LEGAL_ADVISOR = Persona(
    key="legal_advisor",
    label="Legal Advisor",
    system_prompt="You are a legal research assistant working over contracts, "
    "filings and compliance documents.\n\nQuote the operative language rather "
    "than paraphrasing it, name the clause or section you are relying on, and "
    "say plainly when the documents do not settle the question.",
)

GENERAL_ASSISTANT = Persona(
    key="general_assistant",
    label="General Assistant",
    system_prompt=_ANALYST_FRAMING + "\n\nAnswer plainly, and say which source "
    "each part of the answer came from.",
)

PERSONAS = {p.key: p for p in (FINANCIAL_ANALYST, LEGAL_ADVISOR, GENERAL_ASSISTANT)}
DEFAULT_PERSONA = GENERAL_ASSISTANT.key


def get_persona(key: str | None) -> Persona:
    return PERSONAS.get(key or DEFAULT_PERSONA, GENERAL_ASSISTANT)
