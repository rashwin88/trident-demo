"""
Application configuration — all environment variables in one place.

Uses Pydantic BaseSettings to read from .env file with type validation.
Every configurable value in the system lives here. Defaults are set for
local Docker Compose development. Production overrides via .env or
environment variables.

Consumed by every module that needs config (imported as `from config import settings`).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Trident application settings, loaded from .env file.

    All values have sensible defaults for local Docker development.
    Override via environment variables or .env file entries.
    """

    # ── LLM Provider ─────────────────────────────────
    # Which LLM to use for extraction, query answering, and the agent.
    # Options: "openai" (direct), "anthropic", "azure" (Azure OpenAI), "ollama"
    LLM_PROVIDER: str = "anthropic"  # openai | anthropic | ollama
    LLM_MODEL: str = "claude-sonnet-4-5"

    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    AZURE_OPENAI_DEPLOYMENT: str = ""

    # Embedding provider
    EMBEDDING_PROVIDER: str = "openai"  # openai | ollama
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 768

    # Ollama (optional)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Neo4j
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "trident_dev"

    # Milvus
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # Chunking
    CHUNK_SIZE: int = 2048
    CHUNK_OVERLAP: int = 128

    # Extraction density: low | medium | high
    EXTRACTION_DENSITY: str = "medium"

    # Parallel chunk extraction (number of concurrent LLM calls)
    EXTRACTION_CONCURRENCY: int = 4

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
