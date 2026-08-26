"""Run the ingestion pipeline over a folder of uploads."""

from __future__ import annotations

from pathlib import Path

from app.core.config import OUTPUT_DIR, settings
from app.ingestion.chunk_metadata import process_document
from app.ingestion.pdf_processor import (
    docling_parser,
    page_marked_markdown,
    pdf_parser,
    replace_tables_with_docling,
    table_pages_pdf,
)
from app.ingestion.manifest import (
    file_id_for, is_registered, register_db, register_file,
)
from app.ingestion.vector_indexer import index_chunks
from app.retrieval.file_store import SUPPORTED_SUFFIXES, FileAdapter


def load_pdf(pdf, index: bool = True, source: str | None = None) -> int:
    pdf = Path(pdf)
    name = pdf.stem
    # artifacts stay under the readable stem; `source` is the manifest file_id
    # that goes into the Qdrant payload
    source = source or file_id_for(pdf)
    out = OUTPUT_DIR / name
    doc_json = out / f"{name}.json"
    fixed_md = out / f"{name}_fixed.md"

    

    if not doc_json.exists():
        pdf_parser(pdf)

    if not fixed_md.exists():
        if table_pages_pdf(doc_json, pdf):
            docling_parser(out / f"{name}_table_pages.pdf")
            replace_tables_with_docling(
                doc_json, out / f"{name}_docling.json",
                out / f"{name}_docling.md", fixed_md,
            )
        else:
            # No tables, so the docling route can't run — but chunk_metadata
            # still needs the page markers it would have injected.
            page_marked_markdown(doc_json, fixed_md)

    chunks = process_document(fixed_md, out, source=source)
    return index_chunks(chunks) if index else len(chunks)


def load_folder(folder=None, index: bool = True) -> FileAdapter:
    folder = Path(folder) if folder else settings.datasets_dir
    adapter = FileAdapter("datasets", max_rows=settings.SQL_MAX_ROWS)

    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        try:
            if suffix == ".sql":
                adapter.add_sql_dump(p)
            elif suffix in SUPPORTED_SUFFIXES:
                adapter.add_file(p)
            elif suffix == ".pdf" and not is_registered(p):
                load_pdf(p, index=index)
                register_file(p)  # same file_id load_pdf stamped on the chunks
        except Exception as exc:
            print(f"skipped {p.name}: {type(exc).__name__}: {exc}")

    register_db(adapter)  # after the loop, so the schema is complete
    return adapter
