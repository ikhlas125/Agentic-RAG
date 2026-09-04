from typing import Any, TypedDict

from app.retrieval.base_store import DataAdapter
from app.schemas.query_schemas import GroundingJudgment, QueryRequest, QueryResponse
from app.schemas.resolution_schemas import ResolutionOutput

class State(TypedDict):

    request: QueryRequest
    resolution: ResolutionOutput

    adapter: DataAdapter
    db_result: dict[str, Any]
    db_attempts: list[dict[str, Any]]

    doc_chunks: list[Any]
    citations: list[dict]

    response: QueryResponse
    grounded: bool
    grounding_judgment: GroundingJudgment
    grounding_attempts: int