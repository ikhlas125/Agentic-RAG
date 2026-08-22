import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONTENT_LIST_PATH = BACKEND_DIR / "storage" / "Artifacts" / "ml_book" / "txt" / "ml_book_content_list.json"

with open(CONTENT_LIST_PATH, "r") as f:
    data = json.load(f)

unique_types = {item["type"] for item in data}

print(unique_types)