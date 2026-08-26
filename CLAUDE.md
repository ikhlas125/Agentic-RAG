# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Agentic-RAG (Dynamic Agentic Systems)

Agentic query platform over two knowledge bases — a PDF/vector corpus and structured
tabular data — with LangGraph routing each query to the right pipeline.

**Source of truth for scope:** [docs/architecture-plan.md](docs/architecture-plan.md).
Seven phases; every component there is derived from `docs/Dynamic_Agentic_Systems.pdf`.
Do not add features beyond the plan without asking. (`README.md` is empty — don't cite it.)

## Environment

Use the repo venv — the system Python lacks `fastembed`, `qdrant_client`, etc.

```bash
.venv/Scripts/python.exe          # Windows / Git Bash
uv sync                           # install deps (pyproject.toml is authoritative)
```

`uv sync` pulls docling plus a CPU-pinned torch from an explicit index (see
`[tool.uv.sources]`). It is slow and large on a cold cache — that is expected, not a hang.

Run tests and scripts from `backend/`. `backend/tests/conftest.py` puts `backend/` on
`sys.path` so `app.*` resolves:

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest tests/ -q                    # whole suite
cd backend && ../.venv/Scripts/python.exe -m pytest tests/test_ingestion/test_db_loader.py -q
cd backend && ../.venv/Scripts/python.exe -m pytest tests/ -k guard -q           # one test by name
cd backend && ../.venv/Scripts/python.exe scripts/db_agent_demo.py               # 4-stage walkthrough
```

`scripts/db_agent_demo.py` is the fastest way to see the structured path end to end;
stages 1–3 need no API key, stage 4 needs `OPENROUTER_API_KEY`.
`scripts/_parked/react_agent_prototype.py` is the pre-restructure prototype the current
layer split was extracted from — read it for intent, don't import it.

Secrets live in `backend/.env` (gitignored), read through `app.core.config.settings`.
Keys actually present there: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `LANGSMITH_*`,
`HF_TOKEN`, `AGENTROUTER_*`. **There is no `OPENAI_API_KEY`** — code that reads that name
will `KeyError` at import (see Known breakage #1).
Never hardcode a key in a tracked file — it has happened once already in this repo.

## Import convention

**Always `from app.x import y`. Never `from backend.app.x import y`.**

The `backend.` prefix breaks under the project's own path setup — there is no `backend`
package. Four files currently violate this and do not import at all (see Known breakage).

## Layer boundaries

The restructure in commit `cd375fe` split the prototype along these lines. Keep them.

| Layer | Owns | Never does |
|---|---|---|
| `app/ingestion/` | "What sources exist?" — registering, chunking, embedding, upserting | Answer queries |
| `app/retrieval/` | "What do they contain?" — adapters over DuckDB/SQL/Qdrant | Register sources |
| `app/nodes/` | Graph nodes, `state -> state` | Touch a provider SDK or a source-specific branch |
| `app/llm/` | Personas + provider registry | Know about nodes |
| `app/compute/` | Pure-Python math, no LLM | Call a model |

Two abstractions carry this: `app/retrieval/base_store.py::DataAdapter` (one interface,
swappable sources) and `app/llm/provider_registry.py` (nodes ask for a model by persona).
Adding a source or provider must not require editing node code — that is the Phase 7
exit criterion, so preserve it now rather than retrofitting it.

`DataAdapter.run()` **never raises** on bad SQL; it returns `{"ok": False, "error": ...}`.
`db_node.py` depends on this to retry against the error message. Don't "fix" it into
raising.

## The graph (Phase 4 topology)

```
PersonaSelector -> RouterNode -> DocNode  -> AnswerFormatter
                              -> DBNode   -> MathNode -> AnswerFormatter
                              -> SuggestionNode
```

`PersonaSelector` resolves the persona **and binds the LLM** before routing, so every node
downstream finds `state["llm"]` already set. `RouterNode` classifies into the three intents
in `app/core/intent_registry.py` and dispatches through `INTENT_ROUTES` — that indirection
is what lets Phase 7 attach a new DBNode instance without editing router code.

**`app/core/graph_state.py` is empty, so the state contract is currently de-facto**, defined
by whatever `db_node.py` happens to read and write:

| Key | Written by | Read by |
|---|---|---|
| `query`, `persona`, `llm`, `adapter` | PersonaSelector / caller | all nodes |
| `db_result` (`{ok, columns, rows}`) | DBNode | MathNode, AnswerFormatter |
| `db_attempts` (list of `SQLAttempt`) | DBNode | WebSocket trace channel |

Pin this schema down before writing more nodes — every node signature depends on it, and
it is the one file several people will need at once.

**The two acceptance queries** for the whole system, from the spec:
- *"Tell me the Moving Average of MSFT from March to May 2024"* → Router → DBNode → MathNode → Formatter
- *"What clause handles data breach retention?"* → Router → DocNode → Formatter

## The document pipeline (what actually runs)

Four stages in `app/ingestion/pdf_processor.py`, chained by hand — there is no orchestrator:

1. `pdf_parser(pdf)` — pymupdf4llm → `Artifacts/<stem>/<stem>.json` + `.md`, with
   `page_boxes` carrying table bounding boxes and `<!-- page:N -->` markers.
2. `table_pages_pdf(json, pdf)` — extracts just the table-bearing pages into a sub-PDF.
3. `docling_parser(sub_pdf)` — TableFormer ACCURATE re-parse of those pages only.
4. `replace_tables_with_docling(...)` — splices docling's tables back into the pymupdf
   markdown, wrapped in `<!-- table start/end -->` → `<stem>_fixed.md`.

Then `chunk_metadata.py::process_document(fixed_md, out_dir)` header-splits that markdown,
resolves table refs, merges sub-50-token chunks, and writes `chunks_.json`. Then
`vector_indexer.py::index_chunks` embeds and upserts into Qdrant.

**Naming is inconsistent between stages:** `pdf_parser` derives its output dir from
`Path(input).stem`, `docling_parser` from `Path(input).parent.name`. That is why the
chain only works for one specific nested path shape, and why the hardcoded call sites
disagree (Known breakage #3).

## Data on disk

Both knowledge bases have real content already:

- `backend/storage/datasets/` — `customers.csv`, `products.csv`, `sales.csv`, `returns.sql`
  (what `load_datasets()` registers by default).
- `backend/storage/documents/` — `NASDAQ_ATSG_2022.pdf`, `ml_book.pdf`, `ml_book-5.pdf`,
  `doc.pdf`, and `Legal/` with ~15 NDA PDFs.
- `backend/storage/Artifacts/doc/` — a **complete successful run** of all four pipeline
  stages (`doc.json`, `doc.md`, `doc_docling.json/md`, `doc_fixed.md`, `doc_table_pages.pdf`).
  Use it as the reference for what good output looks like. Gitignored.
- `backend/storage/page_images/` — **empty except `.gitkeep`.** Nothing renders page images.
- `output/` — 441 MB of untracked MinerU-style artifacts (per-figure `.jpg` crops under
  `<name>/auto/images/`, plus UUID upload dirs). No code in this repo references MinerU;
  it came from an external tool run. Gitignored in the working tree, not yet committed.

## Status

Empty file = scaffolded stub, not implemented. Check line count before assuming a module works.

| Phase | State |
|---|---|
| 1 — Ingestion & storage | Structured side **done** (`db_loader`, `file_store`, `sql_store`, guard + demo). Document side parses correctly by hand but **does not import** — see below |
| 2 — Nodes | `db_node` done. `doc_node` raises `NotImplementedError`. `math_node` + all of `app/compute/` empty |
| 3 — Personas & providers | `personas.py` + `provider_registry.py` done. `base_provider.py`, `openai_provider.py`, `claude_provider.py`, `deepseek_provider.py` all empty |
| 4 — Orchestration | Only the intent vocabulary exists. `graph_state.py`, `graph_builder.py`, `router_node.py`, `persona_selector.py` empty |
| 5 — API & tracing | `answer_formatter` raises. `main.py`, all `api/routes_*.py`, all `tracing/` empty |
| 6 — Frontend | The full Next.js three-panel tree exists — `app/`, `components/{chat,knowledge-base,layout,personas,source-preview,trace}/`, `hooks/`, `lib/`, `types/` — but **all 29 files are zero bytes**, `package.json` included. The component split is decided; none of it is written |
| 7 — Dynamic expansion | Not started |

## Known breakage — fix before building on top

1. **The document/vector path does not import.** `embedder.py`, `vector_indexer.py`,
   `vector_store.py`, `loader.py` use the `backend.` prefix. Separately, `embedder.py`
   line 14 reads `os.environ["OPENAI_API_KEY"]` while its `_BASE_URL` is already
   OpenRouter — it wants the OpenRouter key under the wrong name, so it `KeyError`s at
   import. Point it at `settings.OPENROUTER_API_KEY`.
2. **`pdf_processor.py` executes four function calls at module scope** (bottom of file).
   `doc.pdf` *does* exist, so importing the module silently runs the entire docling
   pipeline — minutes of compute and real file writes as a side effect of an import.
   Guard behind `if __name__ == "__main__":`.
3. **Stale `NASDAQ_ATSG_2022` paths.** Those module-scope calls write into `Artifacts/doc/`
   but the fourth reads `Artifacts/NASDAQ_ATSG_2022/doc_docling.md`, which was never
   written there — that directory does not exist. `chunk_metadata.py`'s `__main__` and
   `loader.py::load_pdf` carry the same stale paths. Three copies of one bug.
4. **Qdrant point IDs collide across documents — silent data loss.** `chunk_metadata.py`
   renumbers chunks `1..N` *per document*, and `vector_indexer.py` passes that straight
   into `PointStruct(id=...)`. Indexing a second PDF overwrites the first one point for
   point, with no error. Needs an ID derived from `(document, chunk_index)`. This alone
   breaks Phase 7's corpus-wide re-indexing.
5. **The citation contract does not exist yet.** Three layers disagree:

   | Layer | Fields |
   |---|---|
   | `vector_indexer` upserts | `content`, `token_count`, `Header 1..6`, `page_start`, `page_end`, `content_type`, `sections` |
   | `doc_node._HIT_FIELDS` expects | `source`, `page`, `title`, `section`, `image` |
   | Plan requires | page number, chunk image, title, section |

   Nothing in the payload carries **document identity**, so `"MSFT_10K.pdf p.31"` is not
   constructible today. Settle this before writing `doc_node`.
6. **No page screenshot is ever rendered.** Phase 5 and Phase 6 exit criteria both require
   one; `page_images/` is empty and no code writes to it. Zero lines exist, not a partial
   build. (The `output/` MinerU crops are per-figure, not per-page — not a substitute.)
7. **Pinecone vs Qdrant.** The plan and `config.py` say Pinecone; the code is Qdrant with
   hybrid dense+sparse RRF fusion. Qdrant is what actually runs. Reconcile the plan and
   drop the dead Pinecone settings rather than leaving both.
8. **`qdrant_storage/` — 465 MB, 99 files — is tracked in git.** Generated data; must be
   gitignored and purged from history. Gets harder with every branch added.
9. **`backend/tests/test_ingestion/test_db_loader.py` was overwritten** with a 20-line
   scratch script containing a live API key. The original 284-line Phase 1 exit-criteria
   suite is recoverable with `git checkout` on that path.
10. **`app/ingestion/loader.py` is unfinished and untracked.** Besides the `backend.`
    imports, `Path`, `settings`, `adapter`, and `SUPPORTED_SUFFIXES` are all undefined in
    it, its folder loop duplicates `db_loader.load_datasets`, and `def load_pdf(Path)`
    shadows the name then ignores the argument. Decide whether it becomes the document-side
    ingestion entry point or gets deleted. `app/helper/skills.py` is likewise empty,
    untracked, and named nowhere in the plan.

## Conventions

- `from __future__ import annotations` at the top of new modules; typed signatures.
- Module docstrings state the phase and the *reason* for a design choice, not just what
  the code does. Match that density.
- SQL from an LLM always passes `app/helper/sql_guard.py::assert_read_only_sql` first.
  Read-only is enforced there, not at the call site.
