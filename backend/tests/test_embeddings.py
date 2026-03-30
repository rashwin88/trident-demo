from unittest.mock import MagicMock, patch

import pytest

import llm.embeddings as emb_module
from llm.embeddings import (
    EmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


class TestEmbeddingProviderSelection:
    def setup_method(self):
        # Reset singleton between tests
        emb_module._provider = None

    @patch("llm.embeddings.settings")
    def test_openai_selected(self, mock_settings):
        mock_settings.EMBEDDING_PROVIDER = "openai"
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
        mock_settings.EMBEDDING_DIM = 768
        provider = get_embedding_provider()
        assert isinstance(provider, OpenAIEmbeddingProvider)

    @patch("llm.embeddings.settings")
    def test_ollama_selected(self, mock_settings):
        mock_settings.EMBEDDING_PROVIDER = "ollama"
        mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
        mock_settings.OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
        provider = get_embedding_provider()
        assert isinstance(provider, OllamaEmbeddingProvider)

    @patch("llm.embeddings.settings")
    def test_unknown_raises(self, mock_settings):
        mock_settings.EMBEDDING_PROVIDER = "unknown"
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider()


class TestEmbeddingProviderInterface:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]
