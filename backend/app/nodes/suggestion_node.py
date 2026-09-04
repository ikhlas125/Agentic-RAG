from __future__ import annotations

from typing import TypedDict

from app.core.config import settings
from app.core.graph_state import State
from app.llm.provider_registry import get_model

SUGGESTION_PROMPT = """Given the question and the answer, suggest 1-2 natural \
follow-up questions the user might ask next.

Question: {question}

Answer: {answer}

Suggest follow-ups that go deeper on this specific answer — comparisons, \
exceptions, or related details — not generic questions."""


class _SuggestionsOutput(TypedDict):
    suggestions: list[str]


def suggest_queries(llm, question: str, answer: str) -> list[str]:
    suggester = llm.with_structured_output(
        _SuggestionsOutput, method="function_calling", include_raw=True)
    output = suggester.invoke(SUGGESTION_PROMPT.format(question=question, answer=answer))
    parsed = output["parsed"]
    return parsed["suggestions"] if parsed else []


def Suggestion_Agent(state: State) -> State:
    llm = get_model(model=settings.ROUTER_MODEL)

    state['response'].suggestions = suggest_queries(
        llm=llm,
        question=state['request'].question,
        answer=state['response'].answer,
    )
    return state
