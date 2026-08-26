"""Typed payloads for query submission and node-internal structured output."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---- node-internal structured output --------------------------------------

class SQLQueryArgs(BaseModel):
    """What the DBNode asks the persona LLM to produce."""

    sql: str = Field(description="A single read-only SELECT statement.")
    reason: str = Field(
        default="", description="One line on what this query is meant to find.")


# ---- trace / result payloads ----------------------------------------------

class SQLAttempt(BaseModel):
    """One DBNode try, surfaced to the WebSocket trace channel."""

    sql: str
    reason: str = ""
    ok: bool
    error: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    persona: Literal["financial_analyst", "legal_advisor", "general_assistant"] = (
        "general_assistant")
    thread_id: str = "default"


class QueryResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
