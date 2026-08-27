import json
import uuid

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, SparseVectorParams, Modifier,
    PointStruct, SparseVector,
)

from app.core.config import OUTPUT_DIR, settings
from app.ingestion.embedder import embed_texts

_COLLECTION = settings.QDRANT_COLLECTION
_VECTOR_SIZE = 3072

_ID_NAMESPACE = uuid.NAMESPACE_DNS


def _build_client() -> QdrantClient:
    """Qdrant Cloud when QDRANT_URL is set, otherwise a local host/port instance."""
    if settings.QDRANT_URL:
        return QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=60,  # cloud round-trips are slower than localhost
        )
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


_qdrant = _build_client()
_sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")


def _ensure_hybrid_collection():
    if _qdrant.collection_exists(_COLLECTION):
        vectors_config = _qdrant.get_collection(_COLLECTION).config.params.vectors
        if isinstance(vectors_config, dict) and vectors_config.get("dense") and vectors_config["dense"].size == _VECTOR_SIZE:
            return  # already on the named dense+sparse schema with matching dimensions
        _qdrant.delete_collection(_COLLECTION)  # old/mismatched schema, e.g. different embedding model dimensions

    _qdrant.create_collection(
        collection_name=_COLLECTION,
        vectors_config={"dense": VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(modifier=Modifier.IDF)},
    )


def index_chunks(chunks):
    _ensure_hybrid_collection()

    print("embedding")
    texts = [chunk["embedding_text"] for chunk in chunks]
    dense_vectors = embed_texts(texts)
    sparse_vectors = list(_sparse_model.embed(texts))

    print("indexing")
    points = [
        PointStruct(
            id=str(uuid.uuid5(_ID_NAMESPACE, f"{chunk['metadata']['source']}:{chunk['id']}")),
            vector={
                "dense": dense_vec,
                "sparse": SparseVector(indices=sparse_vec.indices.tolist(), values=sparse_vec.values.tolist()),
            },
            payload={
                "content": chunk["content"],
                "token_count": chunk["token_count"],
                "chunk_id": chunk["id"],
                **chunk["metadata"],
            },
        )
        for chunk, dense_vec, sparse_vec in zip(chunks, dense_vectors, sparse_vectors)
    ]

    _qdrant.upsert(collection_name=_COLLECTION, points=points)
    return len(points)


if __name__ == "__main__":
    name = "doc"
    chunks_path = OUTPUT_DIR / name / "chunks_.json"

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    count = index_chunks(chunks)
    print(f"Indexed {count} points into '{_COLLECTION}'")
