from pydantic import BaseModel, Field
from typing import Optional

from app.schemas.query_schemas import SQLQueryArgs


class ResolutionOutput(BaseModel):

    needs_rag: bool = Field(
        description="True if answering the query requires searching unstructured documents (RAG).")
    needs_db: bool = Field(
        description="True if answering the query requires querying a structured/SQL data source.")

    HyDe: str = Field(
        "", description="Hypothetical answer used to improve dense retrieval. Only set when needs_rag is True; leave empty otherwise.")
    Queries: list[str] = Field(
        default_factory=list, description="Search queries to run against the vector store. Only set when needs_rag is True; leave empty otherwise.")
    doc_type: Optional[str] = Field(
        None, description="Restrict RAG search to this domain/category, chosen from the doc_type values found "
        "across the manifest's doc_sources entries (e.g. 'legal_data', 'financial_data'). Only set when "
        "needs_rag is True; leave unset to search all doc_types.")

    SQL_Query: Optional[SQLQueryArgs] = Field(
        None, description="Read-only SQL SELECT statement and reason. Only set when needs_db is True; leave unset otherwise.")

