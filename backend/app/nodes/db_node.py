"""Database Node — executes SQL against the structured knowledge base.

Consumes the shared graph state, writes structured rows back into it, and
either terminates at the AnswerFormatter or feeds the MathNode.

Note on shape: this is a graph node, not a LangChain tool. The adapter's
schema text is injected into the *prompt* rather than a tool description,
and the retry-on-error loop that a ReAct agent performs implicitly is
written out explicitly below — that is what makes each attempt visible to
the trace channel.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.graph_state import State
from app.llm.provider_registry import get_model
from app.retrieval.base_store import DataAdapter
from app.schemas.query_schemas import SQLQueryArgs
from langsmith import traceable

SQL_PROMPT = """Write ONE read-only {dialect} query that answers the question.

Rules:
- Use table and column names exactly as shown below. Never invent them.
- Aggregate in SQL rather than fetching raw rows.
- Do arithmetic in the query, not in your head.

{schema}

Question: {question}"""

MAX_ATTEMPTS = 3


def generate_sql(llm: Any, adapter: DataAdapter, question: str,
                 sample_rows: int | None = None,
                 draft: SQLQueryArgs | None = None) -> tuple[dict[str, Any], list[dict]]:
    """Run a draft SQL query, falling back to LLM drafting/retry on failure.

    `draft`, if given, is RouterNode's `resolution.SQL_Query` (same
    `SQLQueryArgs` shape) — tried first with no LLM call at all. Only a
    failed first attempt, or no draft being given, spends an LLM call here.

    Returns (result, attempts). `result` is the adapter payload — ok/columns/
    rows, or ok=False/error once attempts are exhausted.
    """
    sample_rows = settings.SQL_SAMPLE_ROWS if sample_rows is None else sample_rows
    writer = llm.with_structured_output(SQLQueryArgs, method="function_calling", include_raw=True)

    prompt = SQL_PROMPT.format(
        dialect=adapter.dialect,
        schema=adapter.schema_text(sample_rows=sample_rows),
        question=question,
    )

    result: dict[str, Any] = {"ok": False, "error": "No attempt was made."}
    attempts: list[dict[str, Any]] = []

    for attempt_num in range(MAX_ATTEMPTS):
        if attempt_num == 0 and draft is not None:
            sql_draft = draft
        else:
            output = writer.invoke(prompt)
            sql_draft = output["parsed"]
            if sql_draft is None:
                # Schema mismatch, not a SQL error — same recoverable-by-rewriting
                # treatment as a rejected query, just fed back differently.
                attempts.append({"sql": "", "reason": "", "ok": False, "error": str(output["parsing_error"])})
                prompt += (
                    f"\n\nYour last response did not match the required schema: "
                    f"{output['parsing_error']}\nFix the shape and try again."
                )
                continue

        result = adapter.run(sql=sql_draft.sql)
        attempts.append({
            "sql": sql_draft.sql,
            "reason": sql_draft.reason,
            "ok": result["ok"],
            "error": result.get("error"),
        })
        if result["ok"]:
            break
        # Feed the error back in. A rejected query and a malformed one look
        # the same from here, and both are recoverable by rewriting.
        prompt += f"\n\nYour last query failed: {result['error']}\nFix it."

    return result, attempts

@traceable
def db_node(state: State) -> State:
    """Graph entrypoint: state -> state."""
    adapter: DataAdapter = state["adapter"]
    # Prefer the persona-bound model; fall back to a direct model for
    # standalone use (persona_selector.py doesn't exist yet).
    llm = state.get("llm") or get_model(model=settings.ROUTER_MODEL)
    resolution = state.get("resolution")
    draft = resolution.SQL_Query if resolution is not None else None
    result, attempts = generate_sql(
        llm=llm,
        adapter=adapter,
        question=state["request"].question,
        draft=draft,
    )

    return {"db_result": result, "db_attempts": attempts}    # feeds the WebSocket trace view
