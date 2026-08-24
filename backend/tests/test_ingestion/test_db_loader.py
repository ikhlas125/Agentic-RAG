"""Phase 1 exit criteria for the structured knowledge base.

Two things are proved here:

1. The read-only guard actually holds. It is the only thing standing between
   an LLM-generated string and the database, so the subtle bypasses get
   explicit cases — comment-hidden writes, stacked statements, and
   SELECT ... INTO, which starts with SELECT and would otherwise pass.
2. A direct SQL query returns correct rows, outside of any agent logic.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.helper.sql_guard import UnsafeQueryError, assert_read_only_sql, slug
from app.ingestion.db_loader import load_datasets
from app.retrieval.file_store import FileAdapter


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

ROWS = [
    {"ticker": "MSFT", "trade_date": "2024-03-01", "close": "415.50"},
    {"ticker": "MSFT", "trade_date": "2024-03-02", "close": "417.25"},
    {"ticker": "MSFT", "trade_date": "2024-03-03", "close": "410.00"},
    {"ticker": "AAPL", "trade_date": "2024-03-01", "close": "179.66"},
]


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    """A folder shaped like storage/datasets/: one CSV plus one .sql dump."""
    csv_path = tmp_path / "prices.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)

    (tmp_path / "tickers.sql").write_text(
        "CREATE TABLE tickers (ticker VARCHAR, sector VARCHAR);\n"
        "INSERT INTO tickers VALUES ('MSFT', 'Technology'), ('AAPL', 'Technology');\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def adapter(dataset_dir: Path):
    a = load_datasets(dataset_dir, name="test")
    yield a
    a.close()


# --------------------------------------------------------------------------
# 1. the read-only guard
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select ticker, close from prices where ticker = 'MSFT'",
    "WITH t AS (SELECT 1 AS n) SELECT n FROM t",
    "DESCRIBE prices",
    "EXPLAIN SELECT 1",
    "SELECT 1;",                                   # single trailing semicolon
    "SELECT 1 -- a trailing comment",
    "/* leading block comment */ SELECT 1",
])
def test_allows_reads(sql):
    assert assert_read_only_sql(sql)


@pytest.mark.parametrize("sql", [
    "DROP TABLE prices",
    "DELETE FROM prices",
    "UPDATE prices SET close = 0",
    "INSERT INTO prices VALUES ('X', '2024-01-01', 1)",
    "CREATE TABLE evil (a INT)",
    "TRUNCATE prices",
    "ALTER TABLE prices ADD COLUMN x INT",
    "GRANT SELECT ON prices TO PUBLIC",
    "ATTACH 'other.db' AS other",
    "PRAGMA database_list",
    "COPY prices TO 'out.csv'",
    "INSTALL httpfs",
    "VACUUM",
])
def test_rejects_writes_and_side_effects(sql):
    with pytest.raises(UnsafeQueryError):
        assert_read_only_sql(sql)


def test_rejects_select_into():
    """Starts with SELECT, so only the keyword scan catches it."""
    with pytest.raises(UnsafeQueryError, match="into"):
        assert_read_only_sql("SELECT * INTO copied FROM prices")


def test_rejects_stacked_statements():
    with pytest.raises(UnsafeQueryError, match="Multiple statements"):
        assert_read_only_sql("SELECT 1; DROP TABLE prices")


def test_rejects_write_hidden_behind_a_line_comment():
    """Comment stripping runs BEFORE the keyword scan, so the DROP is seen.

    If stripping ran after, the newline would end the comment and the DROP
    would survive — this is the case that makes the ordering load-bearing.
    """
    with pytest.raises(UnsafeQueryError):
        assert_read_only_sql("SELECT 1 -- harmless\nDROP TABLE prices")


def test_rejects_write_hidden_behind_a_block_comment():
    with pytest.raises(UnsafeQueryError):
        assert_read_only_sql("SELECT 1 /* still\nharmless */ ; DELETE FROM prices")


@pytest.mark.parametrize("sql", ["", "   ", "-- only a comment"])
def test_rejects_empty(sql):
    with pytest.raises(UnsafeQueryError, match="Empty query"):
        assert_read_only_sql(sql)


def test_cleaned_sql_is_returned_without_trailing_semicolon():
    assert assert_read_only_sql("  SELECT 1 ;  ") == "SELECT 1"


@pytest.mark.parametrize("raw,expected", [
    ("MSFT 1y data (final)", "msft_1y_data_final"),
    ("sales.csv", "sales_csv"),
    ("!!!", "source"),
])
def test_slug(raw, expected):
    assert slug(raw) == expected


# --------------------------------------------------------------------------
# 2. ingestion
# --------------------------------------------------------------------------

def test_loads_csv_and_sql_dump(adapter):
    """A dump lands in its own schema, named <stem>_dump, not in main.

    Worth pinning: it means the qualified name is tickers_dump.tickers, which
    is what has to appear in the schema text or the DBNode will write
    FROM tickers and get nothing.
    """
    assert ("main", "prices") in adapter._tables()
    assert ("tickers_dump", "tickers") in adapter._tables()


def test_ignores_unsupported_files(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("not a dataset", encoding="utf-8")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
    a = load_datasets(tmp_path, name="empty")
    assert a._tables() == []
    a.close()


def test_rejects_unsupported_extension_when_added_directly(tmp_path: Path):
    p = tmp_path / "notes.txt"
    p.write_text("x", encoding="utf-8")
    a = FileAdapter("t")
    with pytest.raises(ValueError, match="Unsupported file type"):
        a.add_file(p)
    a.close()


def test_missing_file_raises(tmp_path: Path):
    a = FileAdapter("t")
    with pytest.raises(FileNotFoundError):
        a.add_file(tmp_path / "nope.csv")
    a.close()


def test_colliding_names_are_disambiguated_not_overwritten(dataset_dir, tmp_path):
    """Two uploads called prices.csv must not silently replace each other."""
    other = tmp_path / "second"
    other.mkdir()
    (other / "prices.csv").write_text("ticker,close\nNVDA,900.0\n", encoding="utf-8")

    a = FileAdapter("t")
    first = a.add_file(dataset_dir / "prices.csv")
    second = a.add_file(other / "prices.csv")

    assert first == "prices" and second == "prices_2"
    assert a.run(sql="SELECT COUNT(*) AS n FROM prices")["rows"][0][0] == len(ROWS)
    assert a.run(sql="SELECT COUNT(*) AS n FROM prices_2")["rows"][0][0] == 1
    a.close()


# --------------------------------------------------------------------------
# 3. schema description — this text is the DBNode's entire view of the data
# --------------------------------------------------------------------------

def test_schema_text_names_tables_columns_and_provenance(adapter):
    schema = adapter.schema_text(sample_rows=2)
    assert "prices" in schema
    assert "ticker" in schema and "close" in schema
    assert "prices.csv" in schema                # provenance note
    assert "Read-only SELECT queries only" in schema


def test_schema_text_includes_sample_rows(adapter):
    schema = adapter.schema_text(sample_rows=2)
    assert "sample rows" in schema
    assert "MSFT" in schema


def test_schema_text_omits_samples_when_zero(adapter):
    assert "sample rows" not in adapter.schema_text(sample_rows=0)


def test_schema_is_cached_and_invalidated_on_new_file(adapter, tmp_path):
    first = adapter.schema_text(sample_rows=2)
    assert adapter.schema_text(sample_rows=2) is first      # cache hit

    extra = tmp_path / "extra.csv"
    extra.write_text("a,b\n1,2\n", encoding="utf-8")
    adapter.add_file(extra)

    assert "extra" in adapter.schema_text(sample_rows=2)     # invalidated


# --------------------------------------------------------------------------
# 4. execution — Phase 1 exit criterion
# --------------------------------------------------------------------------

def test_direct_query_returns_correct_rows_for_ticker_and_range(adapter):
    """The plan's Phase 1 exit criterion, stated literally."""
    result = adapter.run(sql="""
        SELECT trade_date, close FROM prices
        WHERE ticker = 'MSFT' AND trade_date BETWEEN '2024-03-01' AND '2024-03-02'
        ORDER BY trade_date
    """)
    assert result["ok"] is True
    assert result["columns"] == ["trade_date", "close"]
    assert result["row_count"] == 2
    assert [r[1] for r in result["rows"]] == [415.50, 417.25]


def test_aggregate_across_csv_and_sql_dump(adapter):
    """A join proves both loaders land in one queryable namespace."""
    result = adapter.run(sql="""
        SELECT t.sector, COUNT(*) AS n
        FROM prices p JOIN tickers_dump.tickers t ON p.ticker = t.ticker
        GROUP BY t.sector
    """)
    assert result["ok"] is True
    assert result["rows"] == [["Technology", 4]]


def test_run_returns_error_instead_of_raising_on_bad_column(adapter):
    """DBNode's retry loop depends on this never raising."""
    result = adapter.run(sql="SELECT no_such_column FROM prices")
    assert result["ok"] is False
    assert "SQL error" in result["error"]


def test_run_returns_error_instead_of_raising_on_rejected_sql(adapter):
    result = adapter.run(sql="DROP TABLE prices")
    assert result["ok"] is False
    assert result["error"].startswith("Rejected:")


def test_results_are_capped_at_max_rows(dataset_dir):
    a = load_datasets(dataset_dir, name="capped")
    a.max_rows = 2
    result = a.run(sql="SELECT * FROM prices")
    assert result["row_count"] == 2
    assert result["truncated"] is True
    a.close()


def test_untruncated_result_is_flagged_as_such(adapter):
    result = adapter.run(sql="SELECT * FROM prices")
    assert result["row_count"] == len(ROWS)
    assert result["truncated"] is False
