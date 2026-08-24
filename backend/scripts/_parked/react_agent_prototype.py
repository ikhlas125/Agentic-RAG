"""PARKED — the ReAct prototype, kept for reference only. Do not import.

Superseded by the architecture plan's explicit StateGraph. Retained because
Phase 4 (core/graph_builder.py) must reproduce what this did:

  - make_tool          -> now app/nodes/db_node.py (schema in prompt, not in a
                          tool description; retry loop written out explicitly)
  - make_document_tool -> now app/nodes/doc_node.py (parked)
  - DEFAULT_SYSTEM_PROMPT -> split across app/llm/personas.py,
                          app/core/intent_registry.py, app/nodes/answer_formatter.py
  - build_agent        -> becomes core/graph_builder.py as a StateGraph, NOT
                          create_react_agent, because a ReAct loop has no
                          discrete nodes for the WebSocket trace view to report.
  - ask / stream       -> becomes app/api/routes_query.py

Original docstring follows.

ORIGINAL:
agent.py — LangGraph orchestration over the adapter layer.

Each adapter becomes ONE LangChain tool whose *description* carries that
source's schema and dialect. That is the whole routing mechanism: the model
picks a tool because the schema in its description matches the question. No
hand-written classifier needed.

Pass a retriever and the same agent handles "what does the 10-K say about
risk factors?" alongside "what was the average closing price in Q3?".

Dependencies: langchain-core, langgraph, pydantic (+ whatever adapters.py
needs). Notably NOT langchain-community, which was sunset in May 2026.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from adapters import DataAdapter, FileAdapter


# --------------------------------------------------------------------------
# Tool argument schemas
# --------------------------------------------------------------------------

class SQLQueryArgs(BaseModel):
    sql: str = Field(description="A single read-only SELECT statement.")
    reason: str = Field(
        default="", description="One line on what this query is meant to find.")


class DocSearchArgs(BaseModel):
    query: str = Field(description="Natural-language search query.")


# --------------------------------------------------------------------------
# Adapter -> LangChain tool
# --------------------------------------------------------------------------

def make_tool(adapter: DataAdapter, sample_rows: int = 2) -> StructuredTool:
    """Wrap an adapter as a StructuredTool with its schema in the description.

    The schema is read ONCE at build time. The model never sees the underlying
    data — only its shape — and fetches rows on demand.
    """
    schema_text = adapter.describe_schema(sample_rows=sample_rows)

    def _run(sql: str, reason: str = "") -> str:
        return json.dumps(adapter.run(sql=sql), default=str, indent=2)

    where = ("files the user uploaded" if isinstance(adapter, FileAdapter)
             else "the live database")

    return StructuredTool.from_function(
        func=_run,
        name=f"query_{adapter.name}",
        description=(
            f"Run a read-only SQL query against {where} ('{adapter.name}'). "
            f"Use for any question involving numbers, aggregates, filtering, "
            f"trends or comparisons over the tables below. Prefer aggregating "
            f"in SQL over fetching raw rows. Use table names exactly as shown. "
            f"IMPORTANT: write {adapter.dialect}.\n\n"
            f"{schema_text}"
        ),
        args_schema=SQLQueryArgs,
    )


def make_document_tool(retriever, name: str = "search_documents",
                       description: str | None = None) -> StructuredTool:
    """Wrap any LangChain retriever (Chroma, pgvector, FAISS...) as a tool, so
    document search sits alongside the SQL tools in the same agent.

    LangChain ships create_retriever_tool, which returns page_content as plain
    concatenated text. This version returns JSON carrying source and page in
    each hit, so the model can cite "MSFT_10K.pdf p.31" rather than gesturing
    vaguely at "the filings".
    """
    def _run(query: str) -> str:
        docs = retriever.invoke(query)
        return json.dumps(
            [
                {"source": d.metadata.get("source", "unknown"),
                 "page": d.metadata.get("page"),
                 "content": d.page_content[:1500]}
                for d in docs
            ],
            indent=2,
        )

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description=description or (
            "Semantic search over the user's uploaded documents (filings, "
            "contracts, reports). Use for questions about wording, policy, "
            "risk factors, legal language or narrative explanation — NOT for "
            "numeric aggregation, which belongs in the SQL tools."
        ),
        args_schema=DocSearchArgs,
    )


# --------------------------------------------------------------------------
# Graph construction
# --------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = """You are a data analyst agent with access to \
structured data sources and (optionally) a document search tool.

Rules:
- Choose the tool whose described schema actually contains the fields needed.
- Numbers, trends, aggregates, comparisons -> query the structured sources.
- Wording, policy, risk factors, narrative or legal language -> search documents.
- A question may need BOTH; run several tools and combine the results.
- Do arithmetic in the query, not in your head.
- If a query errors, read the message, fix it, and retry (max 3 attempts per source).
- Never invent table or column names that are not present in a schema.
- Cite which source each figure came from in your final answer."""


def build_agent(
    adapters: Sequence[DataAdapter],
    model: Any,
    retriever: Any = None,
    extra_tools: Sequence[Any] = (),
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    checkpointer: Any = None,
    sample_rows: int = 2,
):
    """Build a LangGraph ReAct agent over the given adapters.

    Args:
        adapters: your FileAdapter / SQLAdapter instances.
        model: a LangChain chat model, e.g. ChatAnthropic(model="claude-sonnet-4-6").
        retriever: optional vector-store retriever for your PDFs.
        extra_tools: any further tools to expose to the agent.
        checkpointer: optional LangGraph checkpointer for conversation memory,
            e.g. InMemorySaver(), or an AsyncPostgresSaver in production.
        sample_rows: rows shown per table in the schema text. Raising this
            improves generated SQL but costs context on wide schemas.
    """
    tools: list[Any] = [make_tool(a, sample_rows=sample_rows) for a in adapters]

    if retriever is not None:
        tools.append(make_document_tool(retriever))

    tools.extend(extra_tools)

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
        checkpointer=checkpointer,
    )


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

def ask(agent, question: str, thread_id: str = "default") -> str:
    """Run one turn and return the final text."""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content


def stream(agent, question: str, thread_id: str = "default"):
    """Stream messages as they're produced — useful for showing tool calls."""
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="values",
    ):
        yield chunk["messages"][-1]
