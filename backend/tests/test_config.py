from config import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings(
            _env_file=None,
            OPENAI_API_KEY="test-key",
            ANTHROPIC_API_KEY="test-key",
        )
        assert s.LLM_PROVIDER == "anthropic"
        assert s.EMBEDDING_PROVIDER == "openai"
        assert s.EMBEDDING_DIM == 768
        assert s.CHUNK_SIZE == 512
        assert s.CHUNK_OVERLAP == 64

    def test_override(self):
        s = Settings(
            _env_file=None,
            LLM_PROVIDER="openai",
            LLM_MODEL="gpt-4o",
            EMBEDDING_PROVIDER="ollama",
            CHUNK_SIZE=1024,
            OPENAI_API_KEY="k",
            ANTHROPIC_API_KEY="k",
        )
        assert s.LLM_PROVIDER == "openai"
        assert s.LLM_MODEL == "gpt-4o"
        assert s.EMBEDDING_PROVIDER == "ollama"
        assert s.CHUNK_SIZE == 1024
