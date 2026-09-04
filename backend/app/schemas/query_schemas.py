"""Typed payloads for query submission and node-internal structured output."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.llm.personas import DEFAULT_PERSONA, PERSONAS

PersonaKey = Literal[tuple(PERSONAS)]  # type: ignore[valid-type]


# ---- node-internal structured output --------------------------------------

class SQLQueryArgs(BaseModel):
    """What the DBNode asks the persona LLM to produce."""

    sql: str = Field(description="A single read-only SELECT statement.")
    reason: str = Field(
        default="", description="One line on what this query is meant to find.")


class GroundingJudgment(BaseModel):

    reasoning: str = Field(
        description="Walk through each claim in the answer against the "
        "provided context before deciding. Note any retrieved source that "
        "disagrees with a claim, even if the claim is otherwise well-cited.")
    supported: bool = Field(
        description="False if any claim is unsupported by or contradicted by the context.")
    contradicted_claims: list[str] = Field(
        default_factory=list,
        description="Claims the answer makes that a retrieved source actually disagrees with.")
    unused_relevant_sources: list[str] = Field(
        default_factory=list,
        description="Retrieved source ids that bear on the question but the answer never addressed.")
    retry_node: Literal["router_node", "answer_formatter", "none"] = Field(
        default="none",
        description="Which node should retry, if supported is False. "
        "'router_node' if the provided context genuinely seems to be "
        "missing information the question needs — RouterNode is the one "
        "that generates search queries, so retrieval retry goes through it, "
        "not DocNode directly, which only executes whatever queries it's "
        "given. 'answer_formatter' if the needed information IS already "
        "present in the provided context but the answer failed to use it "
        "correctly — worth re-synthesizing, not re-retrieving. "
        "'none' if supported is True.")


# ---- trace / result payloads ----------------------------------------------

class SQLAttempt(BaseModel):
    """One DBNode try, surfaced to the WebSocket trace channel."""

    sql: str
    reason: str = ""
    ok: bool
    error: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    persona: PersonaKey = DEFAULT_PERSONA
    thread_id: str = "default"


class QueryResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
