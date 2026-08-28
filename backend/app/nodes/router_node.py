from app.core.graph_state import State
from langsmith import traceable
from app.llm.provider_registry import get_model
from app.core.config import MANIFEST_PATH, settings
from app.helper.helper import load_json
from app.schemas.resolution_schemas import ResolutionOutput

ROUTER_PROMPT = """Decide how to answer the question using the sources described below.

- Set needs_rag True if the answer requires unstructured document content (wording, \
policy, clauses, narrative, risk factors).
- Set needs_db True if the answer requires structured/tabular data (aggregates, \
counts, joins, numeric lookups).
- A question may need both — set both True and fill in both sets of fields below.
- Only fill in the fields for a branch you set True; leave the other branch's fields \
at their default (empty/unset).

If needs_rag is True:
- HyDe: a short hypothetical passage that would answer the question, phrased the way \
it would appear in a real document. Used to improve dense retrieval.
- Queries: 1-3 short search strings to run against the vector store.
- doc_type: a doc_type value shared by the relevant documents below (e.g. \
'legal_data', 'financial_data') — only set if the question is clearly scoped to that \
category; otherwise leave unset.

If needs_db is True:
- SQL_Query must be an object with two keys — {{"sql": "...", "reason": "..."}} — \
never a plain string.
- SQL_Query.sql: a single read-only SELECT over the tables below, using table and \
column names exactly as shown. This is a first draft only — a downstream node retries \
it against real execution errors, so it does not need to be perfect.
- SQL_Query.reason: one line on what the query is meant to find.

Document sources (doc_sources):
{doc_sources}

Structured sources (db_sources):
{db_sources}

Question: {question}"""


def _format_doc_sources(doc_sources: list[dict]) -> str:
    if not doc_sources:
        return "(none)"
    return "\n".join(
        f"- {entry.get('artifact_name') or entry.get('source', '?')} "
        f"[doc_type={entry.get('doc_type', '?')}]: {entry.get('summary', '')}"
        for entry in doc_sources
    )


def _format_db_sources(db_sources: list[dict]) -> str:
    if not db_sources:
        return "(none)"
    lines = []
    for entry in db_sources:
        columns = ", ".join(
            f"{col['name']} {col['type']}" for col in entry.get("columns", []))
        lines.append(
            f"- {entry.get('qualified_name') or entry.get('name', '?')}({columns}): "
            f"{entry.get('summary', '')}"
        )
    return "\n".join(lines)


MAX_ATTEMPTS = 2


@traceable
def Router_Agent(state: State):
    data_manifest = load_json(MANIFEST_PATH)

    classifier = get_model(
        model=settings.ROUTER_MODEL,
    ).with_structured_output(ResolutionOutput, include_raw=True)

    prompt = ROUTER_PROMPT.format(
        doc_sources=_format_doc_sources(data_manifest.get("doc_sources", [])),
        db_sources=_format_db_sources(data_manifest.get("db_sources", [])),
        question=state["query"],
    )

    resolution = None
    for _ in range(MAX_ATTEMPTS):
        result = classifier.invoke(prompt)
        resolution = result["parsed"]
        if resolution is not None:
            break
        prompt += (
            f"\n\nYour last response did not match the required schema: "
            f"{result['parsing_error']}\nFix the shape and try again."
        )

    state["resolution"] = resolution
    return state
