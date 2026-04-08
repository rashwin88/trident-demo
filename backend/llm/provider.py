import dspy

from config import settings


def get_lm() -> dspy.LM:
    """Return a DSPy LM instance for the configured provider."""
    match settings.LLM_PROVIDER:
        case "openai":
            return dspy.LM(
                f"openai/{settings.LLM_MODEL}",
                api_key=settings.OPENAI_API_KEY,
            )
        case "azure":
            return dspy.LM(
                f"azure/{settings.AZURE_OPENAI_DEPLOYMENT}",
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_base=settings.AZURE_OPENAI_ENDPOINT,
                api_version=settings.AZURE_OPENAI_API_VERSION,
            )
        case "anthropic":
            return dspy.LM(
                f"anthropic/{settings.LLM_MODEL}",
                api_key=settings.ANTHROPIC_API_KEY,
            )
        case "ollama":
            return dspy.LM(
                f"openai/{settings.LLM_MODEL}",
                base_url=f"{settings.OLLAMA_BASE_URL}/v1",
                api_key="ollama",
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
