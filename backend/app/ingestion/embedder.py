import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_MODEL = "openai/text-embedding-3-large"
_BASE_URL = "https://openrouter.ai/api/v1"
_BATCH_SIZE = 100

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=_BASE_URL)


def embed_texts(texts):
    embeddings = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start:start + _BATCH_SIZE]
        response = _client.embeddings.create(input=batch, model=_MODEL)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


