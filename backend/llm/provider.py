"""LLM provider factory -- returns a configured DSPy language model.

Abstracts away the differences between OpenAI, Azure OpenAI, Anthropic, and
Ollama backends behind a single get_lm() call.  The active provider is
selected via config.settings.LLM_PROVIDER.

Consumed by:
    - main.py lifespan hook (calls dspy.configure(lm=get_lm()) at startup)
    - Any module that uses DSPy signatures (indirectly, via the global config)

Key design choices:
    - Ollama is accessed through the OpenAI-compatible /v1 endpoint so that
      DSPy's openai adapter can be reused without a custom integration.
    - Azure requires explicit api_base and api_version, which are separate
      settings from the standard OpenAI key.
"""

import dspy

from config import settings


def get_lm() -> dspy.LM:
    """Return a DSPy LM instance for the configured provider.

    Reads LLM_PROVIDER from settings and constructs the appropriate DSPy LM
    with provider-specific credentials and endpoints.

    Returns:
        dspy.LM: A ready-to-use language model instance.

    Raises:
        ValueError: If LLM_PROVIDER is not one of the supported backends.
    """
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
