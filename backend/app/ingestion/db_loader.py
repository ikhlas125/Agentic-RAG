"""Structured-data ingestion: turn configured or uploaded sources into adapters.

Registering a source is ingestion and lives here; querying one is retrieval
and lives in app/retrieval/. This module is deliberately thin — it owns the
question "what sources exist?", never "what do they contain?".
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.retrieval.base_store import DataAdapter
from app.retrieval.file_store import SUPPORTED_SUFFIXES, FileAdapter
from app.retrieval.sql_store import SQLAdapter


def load_datasets(folder: str | Path | None = None,
                  name: str = "datasets") -> FileAdapter:
    """Register every supported file and .sql dump in a folder.

    Defaults to backend/storage/datasets/, which is where the upload endpoint
    (routes_knowledge_base) will drop user CSVs.
    """
    folder = Path(folder) if folder is not None else settings.datasets_dir
    adapter = FileAdapter(name, max_rows=settings.SQL_MAX_ROWS)

    for p in sorted(folder.glob("*")):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix == ".sql":
            adapter.add_sql_dump(p)
        elif suffix in SUPPORTED_SUFFIXES:
            adapter.add_file(p)

    return adapter


def connect_database(url: str, **kwargs) -> SQLAdapter:
    """Attach a live SQL source.

    Phase 7 calls this once per registered database; each returned adapter
    becomes a DBNode instance attached via the intent registry.
    """
    kwargs.setdefault("max_rows", settings.SQL_MAX_ROWS)
    return SQLAdapter(url, **kwargs)


def build_adapters() -> list[DataAdapter]:
    """All structured sources currently available to the DBNode."""
    adapters: list[DataAdapter] = [load_datasets()]

    if settings.POSTGRES_URI:
        adapters.append(connect_database(settings.POSTGRES_URI, name="warehouse"))

    return adapters
