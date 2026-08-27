import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_FILE = Path(__file__).resolve()

# App, Backend, and Project Root directory resolution
APP_DIR = CONFIG_FILE.parents[1]        # .../backend/app
BACKEND_DIR = CONFIG_FILE.parents[2]    # .../backend
PROJECT_ROOT = CONFIG_FILE.parents[3]   # .../dynamic-agentic-systems

# Storage Directories (backend/storage/...)
STORAGE_DIR = BACKEND_DIR / "storage"
DOCUMENTS_DIR = STORAGE_DIR / "documents"
OUTPUT_DIR = STORAGE_DIR / "Artifacts"
PAGE_IMAGES_DIR = STORAGE_DIR / "page_images"
DATASETS_DIR = STORAGE_DIR / "datasets"
MANIFEST_PATH =  DOCUMENTS_DIR / "manifest.json"

# Ensure runtime storage directories exist
for directory in (DOCUMENTS_DIR, PAGE_IMAGES_DIR, DATASETS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Default Test/Sample Files
ML_BOOK = DOCUMENTS_DIR / "ml_book-5.pdf"


# -----------------------------------------------------------------------------
# Dynamic Application Settings (Pydantic)
# -----------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    Central settings class reading from backend/.env or environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App Config
    PROJECT_NAME: str = "Dynamic Agentic Systems"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Storage Paths (Exposed via Settings)
    storage_dir: Path = STORAGE_DIR
    documents_dir: Path = DOCUMENTS_DIR
    page_images_dir: Path = PAGE_IMAGES_DIR
    datasets_dir: Path = DATASETS_DIR

    # LLM & API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None

    # OpenRouter — light/bulk work: source summaries, SQL drafting, embeddings
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    # GMI Cloud — heavy reasoning (the routing agent). Only the free MiniMax
    # models: "MiniMaxAI/MiniMax-M2.7" and "MiniMaxAI/MiniMax-M3".
    GMI_API_KEY: Optional[str] = None
    GMI_BASE_URL: str = "https://api.gmi-serving.com/v1"
    ROUTER_MODEL: str = "MiniMaxAI/MiniMax-M2.7"

    # Structured-source defaults (DBNode / retrieval adapters)
    SQL_MAX_ROWS: int = 200
    SQL_SAMPLE_ROWS: int = 2

    # Qdrant — Qdrant Cloud when QDRANT_URL is set, else the local host/port
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "agentic_rag"

    # Vector Database & Retrieval Settings
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None
    PINECONE_INDEX_NAME: str = "agentic-index"

    # Databases
    POSTGRES_URI: Optional[str] = "postgresql://user:password@localhost:5432/agentic_db"
    MONGODB_URI: Optional[str] = "mongodb://localhost:27017/agentic_db"



# Singleton instance for import across backend app
settings = Settings()