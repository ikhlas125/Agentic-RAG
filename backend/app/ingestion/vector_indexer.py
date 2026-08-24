import json
import os

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, SparseVectorParams, Modifier,
    PointStruct, SparseVector,
)

from backend.app.ingestion.embedder import embed_texts

_COLLECTION = "agentic_rag"
_VECTOR_SIZE = 3072

_qdrant = QdrantClient(
    host=os.environ.get("QDRANT_HOST", "localhost"),
    port=int(os.environ.get("QDRANT_PORT", 6333)),
)
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
            id=chunk["id"],
            vector={
                "dense": dense_vec,
                "sparse": SparseVector(indices=sparse_vec.indices.tolist(), values=sparse_vec.values.tolist()),
            },
            payload={
                "content": chunk["content"],
                "token_count": chunk["token_count"],
                **chunk["metadata"],
            },
        )
        for chunk, dense_vec, sparse_vec in zip(chunks, dense_vectors, sparse_vectors)
    ]

    _qdrant.upsert(collection_name=_COLLECTION, points=points)
    return len(points)


if __name__ == "__main__":
    name = "NASDAQ_ATSG_2022"
    chunks_path = f"backend/storage/Artifacts/{name}/chunks_.json"

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    count = index_chunks(chunks)
    print(f"Indexed {count} points into '{_COLLECTION}'")
