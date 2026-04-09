"""Embedding provider abstraction -- pluggable vector-embedding backends.

Defines an EmbeddingProvider ABC and concrete implementations for OpenAI
(including Azure OpenAI) and Ollama.  A singleton factory (get_embedding_provider)
returns the provider selected by config.settings.EMBEDDING_PROVIDER.

All consumers should call get_embedding_provider() rather than instantiating
a provider directly, so the backend can be swapped via environment variables
without code changes.

Consumed by:
    - stores.graph_index   (embeds node text for the GN vector index)
    - ingestion.resolver   (indirectly, via graph_index.search)
    - Any future retrieval / RAG paths that need embeddings

Key design choices:
    - OpenAI and Azure share the same class because their APIs are almost
      identical; the constructor selects the right client based on config.
    - Azure does not support the ``dimensions`` parameter, so it is
      conditionally omitted.
    - Ollama's embedding endpoint is not batched server-side, so
      embed_batch falls back to sequential single-embedding calls.
    - The singleton pattern avoids recreating HTTP clients on every call.
"""

from abc import ABC, abstractmethod

import httpx
from openai import AzureOpenAI, OpenAI

from config import settings


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    Subclasses must implement embed (single text) and embed_batch (multiple
    texts).  Callers should prefer embed_batch when possible for throughput.
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for OpenAI and Azure OpenAI.

    Selects the appropriate client (OpenAI vs AzureOpenAI) based on
    EMBEDDING_PROVIDER in settings.  Azure requires a separate endpoint
    and API version and does not support the ``dimensions`` kwarg.
    """

    def __init__(self) -> None:
        if settings.EMBEDDING_PROVIDER == "azure":
            self._client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_version=settings.AZURE_OPENAI_API_VERSION,
            )
        else:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_EMBEDDING_MODEL

    def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        kwargs = dict(input=text, model=self._model)
        # Azure doesn't support the dimensions parameter
        if settings.EMBEDDING_PROVIDER != "azure":
            kwargs["dimensions"] = settings.EMBEDDING_DIM
        resp = self._client.embeddings.create(**kwargs)
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, ordered to match the input list.
            Sorting by index is necessary because the API may return
            results out of order.
        """
        kwargs = dict(input=texts, model=self._model)
        if settings.EMBEDDING_PROVIDER != "azure":
            kwargs["dimensions"] = settings.EMBEDDING_DIM
        resp = self._client.embeddings.create(**kwargs)
        # Sort by index because the API does not guarantee response order
        return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider for locally-hosted Ollama models.

    Uses Ollama's /api/embeddings REST endpoint.  Does not support
    server-side batching, so embed_batch issues sequential requests.
    """

    def __init__(self) -> None:
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.OLLAMA_EMBEDDING_MODEL

    def embed(self, text: str) -> list[float]:
        """Embed a single text string via Ollama's REST API.

        Args:
            text: The text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        with httpx.Client() as client:
            resp = client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts sequentially (Ollama has no batch endpoint).

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        return [self.embed(t) for t in texts]


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the singleton embedding provider for the configured backend.

    Reads EMBEDDING_PROVIDER from settings and instantiates the matching
    concrete class on first call.  Subsequent calls return the cached instance.

    Returns:
        EmbeddingProvider: The configured provider instance.

    Raises:
        ValueError: If EMBEDDING_PROVIDER is not a recognised backend name.
    """
    global _provider
    if _provider is None:
        match settings.EMBEDDING_PROVIDER:
            case "openai" | "azure":
                _provider = OpenAIEmbeddingProvider()
            case "ollama":
                _provider = OllamaEmbeddingProvider()
            case _:
                raise ValueError(
                    f"Unknown embedding provider: {settings.EMBEDDING_PROVIDER}"
                )
    return _provider
