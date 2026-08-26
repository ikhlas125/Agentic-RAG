from typing import Any, TypedDict

from app.retrieval.base_store import DataAdapter
from app.schemas.resolution_schemas import ResolutionOutput

class State(TypedDict):

    query: str
    resolution: ResolutionOutput

    adapter: DataAdapter
    llm: Any
    db_result: dict[str, Any]
    db_attempts: list[dict[str, Any]]