from __future__ import annotations

from app.core.graph_state import State
from app.llm.personas import FINANCIAL_ANALYST, LEGAL_ADVISOR

DOC_TYPE_TO_PERSONA = {
    "financial_data": FINANCIAL_ANALYST.key,
    "legal_data": LEGAL_ADVISOR.key,
}


def assign_persona(state: State) -> State:
    
    resolution = state.get("resolution")
    doc_type = resolution.doc_type if resolution else None
    key = DOC_TYPE_TO_PERSONA.get(doc_type) if doc_type else None
    if key is not None:
        state["request"].persona = key
    return state
