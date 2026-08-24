"""Read-only SQL validation and shared result shaping.

The security boundary for every structured source. Deliberately imports
nothing from the rest of the app so it cannot be weakened by a refactor
elsewhere.
"""

from __future__ import annotations

import re
from typing import Any


_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "grant", "revoke", "attach", "detach", "copy", "export",
    "install", "load", "pragma", "call", "vacuum", "merge", "upsert",
    "commit", "rollback",
    # 'into' catches SELECT * INTO new_table FROM t, which starts with SELECT
    # and would otherwise sail straight through the checks below.
    "into",
}
_ALLOWED_STARTS = ("select", "with", "describe", "show", "explain", "summarize")


class UnsafeQueryError(ValueError):
    """Raised when a generated query isn't a plain read."""


def assert_read_only_sql(sql: str) -> str:
    """Validate a single read-only SQL statement. Returns the cleaned SQL."""
    cleaned = re.sub(r"--[^\n]*", " ", sql)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip().rstrip(";").strip()

    if not cleaned:
        raise UnsafeQueryError("Empty query.")
    if ";" in cleaned:
        raise UnsafeQueryError("Multiple statements are not allowed.")

    first = cleaned.split(None, 1)[0].lower()
    if first not in _ALLOWED_STARTS:
        raise UnsafeQueryError(f"Only read queries allowed; got '{first.upper()}'.")

    bad = set(re.findall(r"[a-zA-Z_]+", cleaned.lower())) & _FORBIDDEN
    if bad:
        raise UnsafeQueryError(f"Forbidden keyword(s): {', '.join(sorted(bad))}")
    return cleaned


def slug(text: str) -> str:
    """'MSFT 1y data (final)' -> 'msft_1y_data_final'."""
    return re.sub(r"\W+", "_", text).strip("_").lower() or "source"


def sample_block(fetcher, sample_rows: int) -> str:
    """Render a few sample rows for the schema text.

    Worth more than it looks: samples show the model that a quarter is
    'FY25Q1' and not '2025-Q1', heading off a whole class of WHERE clauses
    that return zero rows while looking perfectly correct.
    """
    if sample_rows <= 0:
        return ""
    try:
        result = fetcher()
        cols = ([d[0] for d in result.description]
                if getattr(result, "description", None) else list(result.keys()))
        rows = result.fetchall()
    except Exception:
        # Sampling is a nicety, never a reason to fail schema generation.
        return ""
    if not rows:
        return ""

    rendered = "\n".join(
        "    " + ", ".join(f"{c}={v!r}" for c, v in zip(cols, row))[:300]
        for row in rows
    )
    return f"\n  sample rows:\n{rendered}"


def rows_payload(cols, rows, max_rows: int) -> dict[str, Any]:
    return {
        "ok": True,
        "columns": list(cols),
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "truncated": len(rows) == max_rows,
    }
