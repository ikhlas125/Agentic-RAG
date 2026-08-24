"""Answer + Metadata Formatter — convergence point for both answer paths.

Phase 5. Responsible for ensuring every document-derived answer carries its
exact page number and rendered page screenshot, and every figure names the
source it came from.
"""

from __future__ import annotations

CITATION_RULE = """Cite which source each figure or claim came from.

- Figures from a structured source: name the table and the period covered.
- Claims from a document: give the document name, page number and section.
- Never present a number you did not retrieve."""


def answer_formatter(state: dict) -> dict:
    """Graph entrypoint: state -> state."""
    raise NotImplementedError("Phase 5 — depends on the graph state schema.")
