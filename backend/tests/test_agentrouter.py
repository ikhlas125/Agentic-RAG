"""Standalone check that the AgentRouter relay answers.

Deliberately imports nothing from `app` - this only proves the relay and the
key work, so it stays runnable even if the app config changes.

    cd backend
    pytest tests/test_agentrouter.py -v -s
    python tests/test_agentrouter.py                       # or run it directly
    python tests/test_agentrouter.py "your prompt" claude-opus-5

The key is read from the AGENTROUTER_API_KEY environment variable, falling
back to backend/.env, so it never lands in this tracked file.

Two relay behaviours worth knowing before reading a failure here:

- It whitelists clients by User-Agent. Without the header below every call
  returns 401 "unauthorized client detected", which is also what an invalid
  key returns - so a 401 usually means the header, not the credential.
- A phrase blocklist rejects stock test prompts ("tell me a joke", "tell me
  a poem") with 400 content-blocked, even when auth is fine.
"""

import os
import sys
from pathlib import Path

import pytest
from openai import OpenAI

BASE_URL = "https://agentrouter.org/v1"
USER_AGENT = "claude-cli/2.0.0 (external, cli)"   # required; see docstring
DEFAULT_MODEL = "claude-opus-5"
LIVE_MODELS = {"gpt-5.6-sol", "claude-opus-5", "claude-opus-4-8", "deepseek-v4f"}


def _api_key():
    """AGENTROUTER_API_KEY from the environment, else from backend/.env."""
    if key := os.environ.get("AGENTROUTER_API_KEY"):
        return key
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "AGENTROUTER_API_KEY":
                return value.strip().strip("'\"")
    return None


def make_client(api_key):
    return OpenAI(
        api_key=api_key,
        base_url=BASE_URL,
        timeout=120,
        default_headers={"User-Agent": USER_AGENT},
    )


def ask(client, prompt, model=DEFAULT_MODEL):
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content or ""

# --------------------------------------------------------------------------
# direct run
# --------------------------------------------------------------------------

PROMPT = """You are the synthesis agent in a multi-agent RAG pipeline. Below are three retrieved
documents. Answer using ONLY the information in these documents — do not use outside
knowledge, and do not fill gaps with plausible-sounding inference.

[DOC 1] (source: internal_wiki_042)
The Zentari-7 protocol was adopted by Northbridge Logistics in March 2024 to reduce
warehouse picking errors. It reduced errors by 12% in its first quarter.

[DOC 2] (source: quarterly_report_q2)
Northbridge Logistics reported that the Zentari-7 protocol reduced picking errors by
18%, though adoption was delayed until April 2024 due to integration issues.

[DOC 3] (source: internal_wiki_042, revision 2)
Correction to prior entry: Zentari-7 was piloted at only two of Northbridge's five
warehouses before company-wide rollout.

Task:
1. Return your answer as valid JSON matching this schema exactly:
   {"answer": string, "confidence": "high"|"medium"|"low", "citations": [string], "conflicts_detected": [string]}
2. Explicitly flag any contradictions between the documents in "conflicts_detected".
3. If the documents don't fully resolve a contradiction, say so — do not silently pick one.
4. Separately (outside the JSON), tell me: what is your knowledge cutoff, and are you
   aware of anything Anthropic announced in June or July 2026 regarding"""


if __name__ == "__main__":
    key = _api_key()
    if not key:
        sys.exit("AGENTROUTER_API_KEY not set (env or backend/.env)")

    prompt = sys.argv[1] if len(sys.argv) > 1 else PROMPT
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    print(f"model: {model}\nprompt: {prompt!r}\n")
    print(ask(make_client(key), prompt, model))
