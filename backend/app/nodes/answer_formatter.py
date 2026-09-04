from app.core.config import settings
from app.core.graph_state import State
from app.llm.personas import get_persona
from app.llm.provider_registry import get_model
from app.schemas.query_schemas import QueryResponse

CITATION_RULE = """Cite which source each figure or claim came from.

- Figures from a structured source: name the table and the period covered.
- Claims from a document: give the document name, page number and section.
- Never present a number you did not retrieve."""

ANSWER_PROMPT = """{persona_prompt}

{citation_rule}

Context:
{context}

Question: {question}{retry_note}"""

RETRY_NOTE = """

Your previous answer was: {previous_answer}

A reviewer found problems with it: {reasoning}
Contradicted claims: {contradicted_claims}
Relevant sources you didn't use: {unused_relevant_sources}

Write a corrected answer that fixes these specific problems."""


def _format_retry_note(state: State) -> str:
    judgment = state.get('grounding_judgment')
    if not judgment or judgment.retry_node != "answer_formatter":
        return ""
    return RETRY_NOTE.format(
        previous_answer=state['response'].answer,
        reasoning=judgment.reasoning,
        contradicted_claims=judgment.contradicted_claims,
        unused_relevant_sources=judgment.unused_relevant_sources,
    )


def _format_doc_context(chunks: list, citations: list[dict]) -> str:
    if not chunks:
        return "(no retrieved context)"
    return "\n\n".join(
        f"[Source: {cit.get('source')}, p.{cit.get('page_start')}]\n"
        f"{chunk.payload.get('content')}"
        for chunk, cit in zip(chunks, citations)
    )


def _format_db_table(db_result: dict) -> str:
    if not db_result or not db_result.get("ok"):
        error = (db_result or {}).get("error")
        return f"(structured query failed: {error})" if error else "(no structured data retrieved)"
    columns, rows = db_result.get("columns", []), db_result.get("rows", [])
    if not rows:
        return "(structured query returned no rows)"
    header = " | ".join(columns)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    return f"{header}\n{body}"


def Answer_Formatter(state: State) -> State:

    resolution = state.get('resolution')
    needs_rag = resolution.needs_rag if resolution else bool(state.get('doc_chunks'))
    needs_db = resolution.needs_db if resolution else bool(state.get('db_result'))

    citations = state['citations']
    db_table = _format_db_table(state.get('db_result', {})) if needs_db else ""

    if needs_db and not needs_rag:
        state['citations'] = citations
        state['response'] = QueryResponse(answer=db_table, citations=citations)
        return state

    query = state['request'].question
    persona = get_persona(state['request'].persona)

    llm = state.get('llm') or get_model(model=settings.OPENROUTER_MODEL)
    prompt = ANSWER_PROMPT.format(
        persona_prompt=persona.system_prompt,
        citation_rule=CITATION_RULE,
        context=_format_doc_context(state['doc_chunks'], citations),
        question=query,
        retry_note=_format_retry_note(state),
    )

    llm_response = llm.invoke(prompt)

    answer = llm_response.content
    if needs_db:
        answer += f"\n\n{db_table}"

    state['citations'] = citations
    state['response'] = QueryResponse(answer=answer, citations=citations)
    return state
