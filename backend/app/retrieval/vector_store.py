from qdrant_client.http.models import (
    Prefetch, FusionQuery, Fusion,
    Filter, FieldCondition, MatchValue, SparseVector,
)

from app.ingestion.embedder import embed_texts
from app.ingestion.vector_indexer import _qdrant, _COLLECTION, _sparse_model


def hybrid_search(query: str, top_k: int = 10, content_type: str | None = None):
    dense_query = embed_texts([query])[0]
    sparse_query = next(_sparse_model.embed([query]))

    query_filter = None
    if content_type is not None:
        query_filter = Filter(must=[FieldCondition(key="content_type", match=MatchValue(value=content_type))])

    result = _qdrant.query_points(
        collection_name=_COLLECTION,
        prefetch=[
            Prefetch(query=dense_query, using="dense", limit=top_k * 4, filter=query_filter),
            Prefetch(
                query=SparseVector(indices=sparse_query.indices.tolist(), values=sparse_query.values.tolist()),
                using="sparse",
                limit=top_k * 4,
                filter=query_filter,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )
    return result.points
