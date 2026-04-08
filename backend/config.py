from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM provider
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
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # Extraction density: low | medium | high
    EXTRACTION_DENSITY: str = "medium"

    # Parallel chunk extraction (number of concurrent LLM calls)
    EXTRACTION_CONCURRENCY: int = 4

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
