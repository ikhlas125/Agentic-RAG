"""SQLAdapter -> SQLAlchemy -> Postgres, MySQL, SQLite, MSSQL (native driver).

The architecture plan names this the "PostgreSQL access layer"; it is that,
generalised across dialects so Phase 7 can attach an arbitrary user-supplied
database without new node code.

Dependencies: sqlalchemy, plus a driver per live database.
"""

from __future__ import annotations

from typing import Any

from app.helper.sql_guard import (
    UnsafeQueryError,
    assert_read_only_sql,
    rows_payload,
    sample_block,
)
from app.retrieval.base_store import DataAdapter


class SQLAdapter(DataAdapter):
    """Query a live SQL database over its own driver.

    SQLAlchemy provides uniform *introspection*, while the query itself runs
    in the server's native dialect — so indexes, the planner and predicate
    pushdown all behave as the DBA intended.

    Create a read-only role before pointing this at anything real:
        CREATE ROLE rag_ro LOGIN PASSWORD '...';
        GRANT CONNECT ON DATABASE mydb TO rag_ro;
        GRANT USAGE  ON SCHEMA public TO rag_ro;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO rag_ro;

    URL examples:
        postgresql+psycopg://user:pw@host:5432/dbname
        mysql+pymysql://user:pw@host:3306/dbname
        sqlite:///./local.db
        mssql+pyodbc://user:pw@host/db?driver=ODBC+Driver+18+for+SQL+Server
    """

    kind = "sql_database"

    def __init__(self, url: str, name: str | None = None, max_rows: int = 200,
                 include_schemas: list[str] | None = None,
                 include_tables: list[str] | None = None):
        from sqlalchemy import create_engine

        # pool_pre_ping avoids handing out connections the server has dropped.
        self.engine = create_engine(url, pool_pre_ping=True, future=True)
        self.include_schemas = include_schemas
        # On a wide warehouse, restrict this. Every table's DDL and sample
        # rows go into the DBNode prompt, so 200 tables will exhaust the
        # context window before the model reaches the question.
        self.include_tables = include_tables
        super().__init__(name or self.engine.dialect.name, max_rows)

    @property
    def dialect(self) -> str:  # type: ignore[override]
        return f"{self.engine.dialect.name} SQL"

    def describe_schema(self, sample_rows: int = 2) -> str:
        from sqlalchemy import inspect, text

        insp = inspect(self.engine)
        schemas = self.include_schemas or [insp.default_schema_name]
        blocks: list[str] = []

        with self.engine.connect() as conn:
            for sch in schemas:
                for tbl in insp.get_table_names(schema=sch):
                    if self.include_tables and tbl not in self.include_tables:
                        continue

                    qualified = f"{sch}.{tbl}" if sch else tbl
                    cols = insp.get_columns(tbl, schema=sch)
                    block = f"TABLE {qualified}\n" + "\n".join(
                        f"  - {c['name']} ({c['type']})"
                        f"{'' if c.get('nullable', True) else ' NOT NULL'}"
                        for c in cols
                    )

                    # Keys matter a lot for join correctness — without them the
                    # model guesses which columns relate, and guesses wrong.
                    pk = insp.get_pk_constraint(tbl, schema=sch).get(
                        "constrained_columns") or []
                    if pk:
                        block += f"\n  PRIMARY KEY: {', '.join(pk)}"
                    for fk in insp.get_foreign_keys(tbl, schema=sch):
                        block += (
                            f"\n  FOREIGN KEY: {', '.join(fk['constrained_columns'])}"
                            f" -> {fk['referred_table']}"
                            f"({', '.join(fk['referred_columns'])})"
                        )

                    # LIMIT is invalid on MSSQL; sample_block swallows the
                    # failure and simply omits samples there.
                    block += sample_block(
                        lambda t=qualified: conn.execute(
                            text(f"SELECT * FROM {t} LIMIT {sample_rows}")),
                        sample_rows,
                    )
                    blocks.append(block)

        return (f"Dialect: {self.dialect}. Read-only SELECT queries only.\n\n"
                + "\n\n".join(blocks))

    def run(self, sql: str = "", **_) -> dict[str, Any]:
        from sqlalchemy import text
        from sqlalchemy.exc import SQLAlchemyError

        try:
            cleaned = assert_read_only_sql(sql)
        except UnsafeQueryError as e:
            return {"ok": False, "error": f"Rejected: {e}"}

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(cleaned))
                cols = list(result.keys())
                rows = result.fetchmany(self.max_rows)
        except SQLAlchemyError as e:
            return {"ok": False, "error": f"SQL error: {type(e).__name__}: {e}"}
        return rows_payload(cols, rows, self.max_rows)

    def close(self) -> None:
        self.engine.dispose()
