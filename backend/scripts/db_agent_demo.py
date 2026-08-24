"""Walk each stage of structured ingestion + query, without the graph.

    cd backend
    python scripts/db_agent_demo.py
    python scripts/db_agent_demo.py storage/datasets "Revenue by category?"

Stages 1-3 need no API key: ingestion, schema baking, and a manual query
through the exact read-only path DBNode executes against. Stage 4 needs
OPENROUTER_API_KEY in backend/.env.

Phase 1 exit criterion is proved by stage 3 — a direct SQL query returning
correct rows outside of any agent logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings          # noqa: E402
from app.ingestion.db_loader import load_datasets   # noqa: E402


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.datasets_dir
    question = (sys.argv[2] if len(sys.argv) > 2
                else "What's the total revenue by product category?")

    print(f"\n=== Stage 1: ingest every file in {folder} ===")
    adapter = load_datasets(folder)
    for note in adapter._notes:
        print(f"  {note}")

    print("\n=== Stage 2: schema text injected into the DBNode prompt ===")
    print("(this is ALL the model ever sees to decide which table has what)\n")
    print(adapter.schema_text(sample_rows=settings.SQL_SAMPLE_ROWS))

    print("\n=== Stage 3: queries run by hand through adapter.run() ===")
    print("-- deliberately wrong column, the error DBNode retries against --")
    print(adapter.run(sql="SELECT category, SUM(revenue) FROM products"))

    print("\n-- a write, which must be rejected before it reaches DuckDB --")
    print(adapter.run(sql="DROP TABLE sales"))

    print("\n-- corrected query --")
    print(adapter.run(sql="""
        SELECT p.category, SUM(s.quantity * p.price) AS revenue
        FROM sales s JOIN products p ON s.product_id = p.product_id
        GROUP BY p.category
        ORDER BY revenue DESC
    """))

    if not settings.OPENROUTER_API_KEY:
        print("\n=== Stage 4 skipped: OPENROUTER_API_KEY not set ===")
        return

    print(f"\n=== Stage 4: DBNode writes the SQL itself — {question!r} ===\n")
    from app.llm.provider_registry import get_model
    from app.nodes.db_node import generate_sql

    result, attempts = generate_sql(get_model(), adapter, question)
    for i, a in enumerate(attempts, 1):
        status = "ok" if a["ok"] else f"failed: {a['error']}"
        print(f"  attempt {i} ({status})\n    {a['sql']}\n")
    print(result)


if __name__ == "__main__":
    main()
