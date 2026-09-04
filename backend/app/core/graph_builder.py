from langgraph.graph import START, END, StateGraph
from app.core.graph_state import State
from app.nodes.router_node import Router_Agent
from app.nodes.doc_node import Retrieval_Agent
from app.nodes.db_node import db_node
from app.nodes.answer_formatter import Answer_Formatter
from app.nodes.persona_selector import assign_persona
from app.nodes.grounding_node import Grounding_Agent
from app.nodes.suggestion_node import Suggestion_Agent

def route_after_persona(state: State):

    targets = []
    if state['resolution'].needs_rag:
        targets.append("Doc")
    if state['resolution'].needs_db:
        targets.append("DB")

    return targets

def route_after_ground_check(state: State):
    if state['grounded']:
        return "Suggest Queries"
    if state.get('grounding_attempts', 0) >= 2:
        return "Suggest Queries"
    if state['grounding_judgment'].retry_node == "router_node":
        return "Router"
    return "Answer Formatter"


builder = StateGraph(State)

builder.add_node("Router", Router_Agent)
builder.add_node("Doc", Retrieval_Agent)
builder.add_node("DB", db_node)
builder.add_node("Answer Formatter", Answer_Formatter)
builder.add_node("Persona Selector", assign_persona)
builder.add_node("Groundedness Check", Grounding_Agent)
builder.add_node("Suggest Queries", Suggestion_Agent)

builder.add_edge(START, "Router")
builder.add_conditional_edges("Router", route_after_persona, {"Doc": "Doc", "DB": "DB"},)
builder.add_edge("Doc", "Persona Selector")
builder.add_edge("DB", "Persona Selector")
builder.add_edge("Persona Selector", "Answer Formatter")
builder.add_edge("Answer Formatter", "Groundedness Check")
builder.add_conditional_edges(
    "Groundedness Check",
    route_after_ground_check,
    {"Router": "Router", "Answer Formatter": "Answer Formatter", "Suggest Queries": "Suggest Queries"},
)
builder.add_edge("Suggest Queries", END)

graph = builder.compile()