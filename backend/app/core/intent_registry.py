"""Intent -> node mapping. Makes routing extensible rather than hardcoded.

Phase 4. Only the intent vocabulary and the classification guidance live
here so far; RouterNode consumes both. The prototype agent got this routing
for free from tool descriptions — under the plan it becomes explicit, so
that the trace channel can report which branch actually fired.
"""

from __future__ import annotations

from typing import Literal

Intent = Literal["mathematical", "factual", "conversational"]

# The three query types the specification names.
INTENTS: dict[Intent, str] = {
    "mathematical": "Stock trends, moving averages, thresholds, aggregates, "
                    "comparisons — anything whose answer is computed.",
    "factual": "Specific document-grounded questions: wording, policy, risk "
               "factors, clauses, legal or narrative language.",
    "conversational": "Multi-step or suggestion-driven dialogue with no single "
                      "retrieval target.",
}

CLASSIFIER_GUIDANCE = """Classify the query into exactly one intent.

- Numbers, trends, aggregates and comparisons -> mathematical
- Wording, policy, risk factors, narrative or legal language -> factual
- Open-ended follow-up or clarification -> conversational

Choose based on which source could actually contain the fields needed."""

# Populated at runtime: intent -> node names. Phase 7 registers a newly
# attached database here so it reaches the RouterNode without a code change.
INTENT_ROUTES: dict[Intent, list[str]] = {
    "mathematical": ["db_node", "math_node"],
    "factual": ["doc_node"],
    "conversational": ["suggestion_node"],
}
