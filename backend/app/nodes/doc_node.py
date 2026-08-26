"""Document RAG Node — similarity search across the indexed corpus.

PARKED / INCOMPLETE. Carried over from the prototype agent so the JSON-with-
metadata shape is not lost, but this cannot be finished yet:

The architecture plan requires each hit to carry the four-field citation
contract — page number, chunk image, title, section — established at
ingestion time by chunk_metadata.py and written by vector_indexer.py. Those
fields are not settled yet (vector_indexer.py is empty on this branch and is
being built on `retrival_embedder`), so `_HIT_FIELDS` below is a placeholder
and must be reconciled with whatever the indexer actually upserts.

Kept deliberately: returning JSON with per-hit metadata rather than
LangChain's create_retriever_tool, which concatenates page_content into
plain text and loses the ability to cite "MSFT_10K.pdf p.31".
"""

from __future__ import annotations

import json
from typing import Any

# TODO: reconcile with the payload vector_indexer.py actually writes.
_HIT_FIELDS = ("source", "page_start", "page_end", "sections", "content_type")
MAX_CHARS = 1500


def search_documents(retriever: Any, query: str) -> str:
    """Run similarity search and return JSON carrying citation metadata."""
    docs = retriever.invoke(query)
    return json.dumps(
        [
            {
                **{f: d.metadata.get(f) for f in _HIT_FIELDS},
                "content": d.page_content[:MAX_CHARS],
            }
            for d in docs
        ],
        default=str,
        indent=2,
    )


def doc_node(state: dict) -> dict:
    """Graph entrypoint: state -> state."""
    raise NotImplementedError(
        "DocNode is blocked on vector_indexer.py — see module docstring.")
