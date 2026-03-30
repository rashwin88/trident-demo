from abc import ABC, abstractmethod

import httpx
from openai import OpenAI

from config import settings


class EmbeddingProvider(ABC):
    """Abstract embedding provider — swap implementations via config."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_EMBEDDING_MODEL

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(
            input=text,
            model=self._model,
            dimensions=settings.EMBEDDING_DIM,
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(
            input=texts,
            model=self._model,
            dimensions=settings.EMBEDDING_DIM,
        )
        return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.OLLAMA_EMBEDDING_MODEL

    def embed(self, text: str) -> list[float]:
        with httpx.Client() as client:
            resp = client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the singleton embedding provider for the configured backend."""
    global _provider
    if _provider is None:
        match settings.EMBEDDING_PROVIDER:
            case "openai":
                _provider = OpenAIEmbeddingProvider()
            case "ollama":
                _provider = OllamaEmbeddingProvider()
            case _:
                raise ValueError(
                    f"Unknown embedding provider: {settings.EMBEDDING_PROVIDER}"
                )
    return _provider
