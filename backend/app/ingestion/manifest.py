"""Source catalog the router reads: one entry per document, one per table."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from app.core.config import MANIFEST_PATH, OUTPUT_DIR
from app.llm.provider_registry import get_model

DOC_TYPES = ("financial_data", "legal_data", "other")

_DOC_PROMPT = """Here is the first page of a document called "{name}" ({pages} pages).

{text}

Reply with only a JSON object:
{{"doc_type": one of {types}, "summary": "2-3 sentences on what this document \
covers and what questions it could answer"}}"""

_TABLE_PROMPT = """Table "{name}" in a {dialect} database.

Columns:
{columns}

Sample rows:
{samples}

Reply with only a JSON object:
{{"summary": "1-2 sentences on what this table holds and what questions it \
could answer"}}"""


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"doc_sources": [], "db_sources": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    # write to temp then replace, so a crash can't leave unparseable JSON
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MANIFEST_PATH)


def _describe(prompt: str) -> dict:
    try:
        reply = get_model().invoke(prompt).content
        return json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
    except Exception as exc:
        print(f"  summary failed: {type(exc).__name__}: {exc}")
        return {}


def _upsert(entries: list, key: str, value: str, entry: dict) -> list:
    return [e for e in entries if e.get(key) != value] + [entry]


def file_id_for(pdf) -> str:
    """Stable id from file content: same bytes -> same id, on any machine."""
    digest = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_OID, digest))


def is_registered(pdf) -> bool:
    digest = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
    return any(e.get("sha256") == digest for e in load_manifest()["doc_sources"])


def register_file(pdf, artifact_name: str | None = None) -> dict:
    pdf = Path(pdf)
    artifact_name = artifact_name or pdf.stem
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    file_id = str(uuid.uuid5(uuid.NAMESPACE_OID, digest))

    manifest = load_manifest()
    for entry in manifest["doc_sources"]:
        if entry.get("sha256") == digest:
            return entry

    pages = json.loads(
        (OUTPUT_DIR / artifact_name / f"{artifact_name}.json").read_text(encoding="utf-8")
    )
    info = _describe(_DOC_PROMPT.format(
        name=pdf.name,
        pages=len(pages),
        text=pages[0]["text"][:3000],
        types=list(DOC_TYPES),
    ))

    entry = {
        "file_id": file_id,  # also the `source` in every Qdrant payload
        "source": pdf.name,
        "artifact_name": artifact_name,
        "sha256": digest,
        "doc_type": info.get("doc_type", "other"),
        "summary": info.get("summary", ""),
        "pages": len(pages),
    }
    manifest["doc_sources"] = _upsert(
        manifest["doc_sources"], "file_id", file_id, entry)
    save_manifest(manifest)
    return entry


def _columns_by_table(adapter) -> dict:
    """{(schema, table): [{name, type}, ...]} read through the adapter."""
    result = adapter.run(
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
        "ORDER BY table_schema, table_name, ordinal_position"
    )
    columns: dict = {}
    for schema, table, name, dtype in result.get("rows", []):
        columns.setdefault((schema, table), []).append({"name": name, "type": dtype})
    return columns


def register_db(adapter, db_id: str | None = None) -> list[dict]:
    """One entry per table, so the router can pick a single table."""
    db_id = db_id or adapter.name
    dialect = getattr(adapter, "dialect", "SQL")
    manifest = load_manifest()
    entries = []

    sources = getattr(adapter, "sources", {})

    for (schema, table), columns in _columns_by_table(adapter).items():
        # bare name in `main`; .sql dumps get their own schema and need it
        qualified = table if schema == "main" else f"{schema}.{table}"
        quoted = f'"{table}"' if schema == "main" else f'"{schema}"."{table}"'
        table_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{db_id}:{qualified}"))
        digest = hashlib.sha256(
            json.dumps([qualified, columns], sort_keys=True).encode()
        ).hexdigest()

        known = next((e for e in manifest["db_sources"]
                      if e.get("table_id") == table_id
                      and e.get("sha256") == digest), None)
        if known:
            entries.append(known)
            continue

        sample = adapter.run(f"SELECT * FROM {quoted} LIMIT 3")
        info = _describe(_TABLE_PROMPT.format(
            name=qualified,
            dialect=dialect,
            columns="\n".join(f"  - {c['name']} ({c['type']})" for c in columns),
            samples=json.dumps(sample.get("rows", []), default=str)[:1500],
        ))

        entry = {
            "table_id": table_id,
            "name": table,
            "schema": schema,
            "qualified_name": qualified,  # what SQL must actually reference
            "source": sources.get(table) or sources.get(schema, ""),
            "db_id": db_id,
            "kind": adapter.kind,
            "dialect": dialect,
            "sha256": digest,
            "columns": columns,
            "summary": info.get("summary", ""),
        }
        manifest["db_sources"] = _upsert(
            manifest["db_sources"], "table_id", table_id, entry)
        entries.append(entry)

    save_manifest(manifest)
    return entries
