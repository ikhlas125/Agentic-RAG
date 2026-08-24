"""Common interface every structured data source must satisfy.

Mirrors app/llm/base_provider.py: one interface, swappable implementations,
so DBNode never contains a source-specific branch.

    .name               -> unique, tool-safe identifier
    .dialect            -> SQL flavour, stated in the prompt given to the LLM
    .describe_schema()  -> text injected into the DBNode prompt
    .run(sql=...)       -> validated, read-only execution -> dict
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.helper.sql_guard import slug


class DataAdapter(ABC):
    """Common interface every data source must satisfy."""

    kind: str = "generic"
    dialect: str = "standard SQL"

    def __init__(self, name: str, max_rows: int = 200):
        self.name = slug(name)
        self.max_rows = max_rows
        self._schema_cache: dict[int, str] = {}

    @abstractmethod
    def describe_schema(self, sample_rows: int = 2) -> str:
        """LLM-readable description of what's queryable here."""

    @abstractmethod
    def run(self, sql: str = "", **kwargs) -> dict[str, Any]:
        """Execute a read-only query.

        Never raises on bad input — returns {'ok': False, 'error': ...}. This
        is what lets DBNode recover: it reads 'column not found', fixes the
        name and retries, instead of the run dying on a typo.
        """

    # ---- schema caching --------------------------------------------------

    def schema_text(self, sample_rows: int = 2) -> str:
        """Cached describe_schema().

        The schema is fixed once ingestion is done, but DBNode needs it on
        every query. Re-introspecting a live database per question is a
        round-trip nobody asked for, so cache it here and let ingestion
        invalidate.
        """
        if sample_rows not in self._schema_cache:
            self._schema_cache[sample_rows] = self.describe_schema(sample_rows)
        return self._schema_cache[sample_rows]

    def invalidate_schema(self) -> None:
        """Call after registering a new table/file on this adapter."""
        self._schema_cache.clear()

    def close(self) -> None:  # pragma: no cover - optional override
        pass
