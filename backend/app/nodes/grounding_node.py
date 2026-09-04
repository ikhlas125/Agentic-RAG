from __future__ import annotations

from app.core.config import settings
from app.core.graph_state import State
from app.llm.provider_registry import get_model
from app.schemas.query_schemas import GroundingJudgment

JUDGE_PROMPT = """Question: {question}

Retrieved context (every source retrieved, not just what the answer used):
{full_context}

Drafted answer:
{answer}

Check the answer against the full retrieved context above. For each claim, \
confirm it's supported. Flag any claim a retrieved source actually disagrees \
with, even if the answer cites a real page for it. Flag any retrieved source \
that's clearly relevant to the question but the answer never addressed.

If the answer isn't fully supported, decide where the fix belongs:
- router_node: the retrieved context above genuinely seems to be missing \
information the question needs — a different search would likely find it.
- answer_formatter: the needed information IS already in the context above, \
the answer just failed to use it — re-writing the answer would fix it, not \
retrieving more."""


def _format_full_context(chunks: list, citations: list[dict]) -> str:
    if not chunks:
        return "(no retrieved context)"
    return "\n\n".join(
        f"[Source: {cit.get('source')}, p.{cit.get('page_start')}]\n"
        f"{chunk.payload.get('content')}"
        for chunk, cit in zip(chunks, citations)
    )


def judge_grounding(llm, question: str, full_context: str, answer: str) -> GroundingJudgment:
    
    judge = llm.with_structured_output(GroundingJudgment)
    return judge.invoke(JUDGE_PROMPT.format(
        question=question, full_context=full_context, answer=answer))


def Grounding_Agent(state: State) -> State:
    state['grounding_attempts'] = state.get('grounding_attempts', 0) + 1

    llm = state.get('llm') or get_model(model=settings.OPENROUTER_MODEL)
    full_context = _format_full_context(state['doc_chunks'], state['citations'])

    judgment = judge_grounding(
        llm=llm,
        question=state['request'].question,
        full_context=full_context,
        answer=state['response'].answer,
    )

    state['grounding_judgment'] = judgment
    state['grounded'] = judgment.supported
    return state
