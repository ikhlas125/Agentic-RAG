"""Covers the three bugs that made a folder loader impossible before."""

from __future__ import annotations

import json

import pytest

from app.ingestion import doc_loader
from app.ingestion.manifest import file_id_for
from app.ingestion.pdf_processor import page_marked_markdown


@pytest.fixture(autouse=True)
def isolate_manifest(tmp_path, monkeypatch):
    """Keep tests out of the real manifest, and off the network."""
    from app.ingestion import manifest
    monkeypatch.setattr(manifest, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(manifest, "_describe", lambda prompt: {})


def _page(n, text, table=False):
    return {
        "metadata": {"page_number": n, "file_path": "sample.pdf"},
        "text": text,
        "page_boxes": [{"class": "table", "pos": [0, 5], "bbox": [0, 0, 10, 10]}]
        if table else [{"class": "text", "pos": [0, 5], "bbox": [0, 0, 10, 10]}],
    }


@pytest.fixture
def pdf(tmp_path, monkeypatch):
    """A fake PDF whose parse stage writes a table-free doc.json."""
    monkeypatch.setattr(doc_loader, "OUTPUT_DIR", tmp_path / "Artifacts")
    p = tmp_path / "sample.pdf"
    p.write_bytes(b"%PDF-1.4")

    def fake_parse(path, name=None):
        out = (tmp_path / "Artifacts") / (name or "sample")
        out.mkdir(parents=True, exist_ok=True)
        (out / "sample.json").write_text(
            json.dumps([_page(1, "# A\n\nx " * 40), _page(2, "# B\n\ny " * 40)]),
            encoding="utf-8",
        )

    monkeypatch.setattr(doc_loader, "pdf_parser", fake_parse)
    return p


def test_table_free_pdf_reaches_chunks(pdf, tmp_path):
    """This path dead-ended before: no tables meant no _fixed.md."""
    assert doc_loader.load_pdf(pdf, index=False) > 0
    assert (tmp_path / "Artifacts" / "sample" / "sample_fixed.md").exists()


def test_chunks_carry_source_and_pages(pdf, tmp_path):
    """Without source the DocNode can't cite; without markers there are no pages."""
    doc_loader.load_pdf(pdf, index=False)
    chunks = json.loads(
        (tmp_path / "Artifacts" / "sample" / "chunks_.json").read_text(encoding="utf-8")
    )

    # source is the manifest file_id, so the router can filter Qdrant by it
    assert {c["metadata"]["source"] for c in chunks} == {file_id_for(pdf)}
    assert max(c["metadata"]["page_end"] for c in chunks) == 2


def test_documents_do_not_overwrite_each_other(monkeypatch):
    """Chunk ids restart at 1 per document; Qdrant point ids must not."""
    qdrant = pytest.importorskip("qdrant_client")
    import app.ingestion.vector_indexer as vi

    monkeypatch.setattr(vi, "_qdrant", qdrant.QdrantClient(":memory:"))
    monkeypatch.setattr(vi, "embed_texts",
                        lambda t: [[0.01] * vi._VECTOR_SIZE for _ in t])

    def chunks(source):
        return [{"id": i, "content": "c", "embedding_text": "c", "token_count": 1,
                 "metadata": {"source": source}} for i in range(1, 6)]

    vi.index_chunks(chunks("a"))
    vi.index_chunks(chunks("b"))
    assert vi._qdrant.get_collection(vi._COLLECTION).points_count == 10

    vi.index_chunks(chunks("a"))  # re-ingest updates in place
    assert vi._qdrant.get_collection(vi._COLLECTION).points_count == 10


def test_folder_dispatches_by_suffix(tmp_path, monkeypatch):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "sales.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
    (folder / "notes.txt").write_text("ignore", encoding="utf-8")

    adapter = doc_loader.load_folder(folder, index=False)

    assert [t[1] for t in adapter._tables()] == ["sales"]


def test_one_bad_file_does_not_abort_the_folder(tmp_path, monkeypatch):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"not a pdf")
    (folder / "sales.csv").write_text("id\n1\n", encoding="utf-8")

    monkeypatch.setattr(doc_loader, "pdf_parser",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    adapter = doc_loader.load_folder(folder, index=False)

    assert [t[1] for t in adapter._tables()] == ["sales"]


def test_page_marked_markdown_emits_one_marker_per_page(tmp_path):
    doc_json = tmp_path / "d.json"
    doc_json.write_text(json.dumps([_page(n, f"body {n}") for n in (1, 2, 3)]),
                        encoding="utf-8")
    out = tmp_path / "out.md"

    page_marked_markdown(doc_json, out)

    assert out.read_text(encoding="utf-8").count("<!-- page:") == 3
