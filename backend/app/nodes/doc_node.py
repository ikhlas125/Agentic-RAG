from app.core.graph_state import State
from langsmith import traceable
from app.retrieval.vector_store import hybrid_search, rerank

MAX_CONTEXT_CHUNKS = 5


@traceable
def Retrieval_Agent(state: State):
    resolution = state['resolution']

    queries = list(resolution.Queries)

    chunks = {}
    for query in queries:
        for point in hybrid_search(query, doc_type=resolution.doc_type):
            if point.id not in chunks or point.score > chunks[point.id].score:
                chunks[point.id] = point

    candidates = list(chunks.values())
    if not candidates:
        return {"doc_chunks": [], "citations": []}

    results = rerank(
        state['request'].question,
        [point.payload['content'] for point in candidates],
        top_n=MAX_CONTEXT_CHUNKS,
    )
    doc_chunks = [candidates[r['index']] for r in results]
    citations = [
        {
            "source": point.payload.get("source"),
            "page_start": point.payload.get("page_start"),
            "page_end": point.payload.get("page_end"),
            "sections": point.payload.get("sections"),
            "doc_type": point.payload.get("doc_type"),
            "pdf_path": point.payload.get("pdf_path"),
            "bbox": point.payload.get("bbox")
        }
        for point in doc_chunks
    ]
    return {"doc_chunks": doc_chunks, "citations": citations}
