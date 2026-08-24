"""FileAdapter -> DuckDB -> CSV / TSV / Parquet / JSON / .sql dumps.

Uploaded files are queried in place, with no ETL step: each file becomes a
DuckDB view and DuckDB reads it off disk on demand.

Not one of the three retrieval slots the architecture plan names (Pinecone /
SQL / Mongo), because DuckDB-over-uploads is none of those.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.helper.sql_guard import (
    UnsafeQueryError,
    assert_read_only_sql,
    rows_payload,
    sample_block,
    slug,
)
from app.retrieval.base_store import DataAdapter


_FILE_READERS = {
    ".csv": "read_csv_auto('{p}')",
    ".tsv": "read_csv_auto('{p}')",
    ".parquet": "read_parquet('{p}')",
    ".json": "read_json_auto('{p}')",
    ".jsonl": "read_json_auto('{p}')",
}

SUPPORTED_SUFFIXES = frozenset(_FILE_READERS)


class FileAdapter(DataAdapter):

    kind = "duckdb_files"
    dialect = "DuckDB SQL (PostgreSQL-compatible)"

    def __init__(self, name: str = "files", max_rows: int = 200):
        import duckdb

        self._duckdb = duckdb
        self.con = duckdb.connect(":memory:")
        self._notes: list[str] = []
        super().__init__(name, max_rows)

    # ---- ingestion -------------------------------------------------------

    def add_file(self, path: str | Path, table_name: str | None = None) -> str:
        """Register a CSV/TSV/Parquet/JSON file as a queryable view."""
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(p)

        ext = p.suffix.lower()
        if ext not in _FILE_READERS:
            raise ValueError(
                f"Unsupported file type {ext}; expected one of {sorted(_FILE_READERS)}")

        table = self._unique_name(table_name or p.stem)
        reader = _FILE_READERS[ext].format(p=str(p).replace("'", "''"))
        self.con.execute(
            f'CREATE OR REPLACE VIEW "{table}" AS SELECT * FROM {reader}')
        self._notes.append(f"{table}  <- {p.name}")
        self.invalidate_schema()
        return table

    def add_sql_dump(self, path: str | Path, schema: str | None = None) -> str:
        """Execute a user-supplied .sql dump into its own DuckDB schema.

        Trusted input: the user handed us this file and it is never
        LLM-generated, so it bypasses the read-only guard by design.
        """
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(p)

        sch = slug(schema or f"{p.stem}_dump")
        self.con.execute(f'CREATE SCHEMA IF NOT EXISTS "{sch}"')
        self.con.execute(f'USE "{sch}"')
        try:
            self.con.execute(p.read_text(encoding="utf-8", errors="replace"))
        finally:
            self.con.execute("USE memory.main")   # restore even on failure
        self._notes.append(f"schema {sch}  <- {p.name} (SQL dump)")
        self.invalidate_schema()
        return sch

    def _unique_name(self, desired: str) -> str:
        """Sanitise, and disambiguate rather than collide.

        Two uploads called sales.csv would otherwise both want the table
        'sales'; the second silently replaces the first.
        """
        base = slug(desired)
        existing = {t for _, t in self._tables()}
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    # ---- introspection ---------------------------------------------------

    def _tables(self) -> list[tuple[str, str]]:
        rows = self.con.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY 1, 2
            """
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def describe_schema(self, sample_rows: int = 2) -> str:
        blocks: list[str] = []
        for schema, table in self._tables():
            q = f'"{table}"' if schema == "main" else f'"{schema}"."{table}"'
            cols = self.con.execute(
                """
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                [schema, table],
            ).fetchall()
            block = f"TABLE {q}\n" + "\n".join(f"  - {c} ({t})" for c, t in cols)
            block += sample_block(
                lambda q=q: self.con.execute(f"SELECT * FROM {q} LIMIT {sample_rows}"),
                sample_rows,
            )
            blocks.append(block)

        notes = "\n".join(f"  * {n}" for n in self._notes)
        return (
            f"Dialect: {self.dialect}. Read-only SELECT queries only.\n"
            f"Loaded from:\n{notes}\n\n" + "\n\n".join(blocks)
        )

    # ---- execution -------------------------------------------------------

    def run(self, sql: str = "", **_) -> dict[str, Any]:
        try:
            cleaned = assert_read_only_sql(sql)
        except UnsafeQueryError as e:
            return {"ok": False, "error": f"Rejected: {e}"}

        try:
            rel = self.con.execute(cleaned)
            cols = [d[0] for d in rel.description] if rel.description else []
            rows = rel.fetchmany(self.max_rows)
        except self._duckdb.Error as e:
            return {"ok": False, "error": f"SQL error: {e}"}
        return rows_payload(cols, rows, self.max_rows)

    def close(self) -> None:
        self.con.close()
