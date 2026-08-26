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
from app.retrieval.base_store import DataAdapter
from app.schemas.query_schemas import SQLQueryArgs

SQL_PROMPT = """Write ONE read-only {dialect} query that answers the question.

Rules:
- Use table and column names exactly as shown below. Never invent them.
- Aggregate in SQL rather than fetching raw rows.
- Do arithmetic in the query, not in your head.

{schema}

Question: {question}"""

MAX_ATTEMPTS = 3


def generate_sql(llm: Any, adapter: DataAdapter, question: str,
                 sample_rows: int | None = None) -> tuple[dict[str, Any], list[dict]]:
    """Draft SQL, run it, and retry against the error message on failure.

    Returns (result, attempts). `result` is the adapter payload — ok/columns/
    rows, or ok=False/error once attempts are exhausted.
    """
    sample_rows = settings.SQL_SAMPLE_ROWS if sample_rows is None else sample_rows
    writer = llm.with_structured_output(SQLQueryArgs)

    prompt = SQL_PROMPT.format(
        dialect=adapter.dialect,
        schema=adapter.schema_text(sample_rows=sample_rows),
        question=question,
    )

    result: dict[str, Any] = {"ok": False, "error": "No attempt was made."}
    attempts: list[dict[str, Any]] = []

    for _ in range(MAX_ATTEMPTS):
        draft = writer.invoke(prompt)
        result = adapter.run(sql=draft.sql)
        attempts.append({
            "sql": draft.sql,
            "reason": draft.reason,
            "ok": result["ok"],
            "error": result.get("error"),
        })
        if result["ok"]:
            break
        # Feed the error back in. A rejected query and a malformed one look
        # the same from here, and both are recoverable by rewriting.
        prompt += f"\n\nYour last query failed: {result['error']}\nFix it."

    return result, attempts


def db_node(state: State) -> State:
    """Graph entrypoint: state -> state."""
    adapter: DataAdapter = state["adapter"]
    result, attempts = generate_sql(
        llm=state["llm"],              # bound upstream by persona_selector
        adapter=adapter,
        question=state["query"],
    )

    state["db_result"] = result
    state["db_attempts"] = attempts    # feeds the WebSocket trace view
    return state
