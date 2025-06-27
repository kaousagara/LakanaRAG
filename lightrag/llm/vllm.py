import os
import pipmaster as pm  # Pipmaster for dynamic library install

# Ensure required libraries are installed
if not pm.is_installed("openai"):
    pm.install("openai")

from .openai import openai_complete_if_cache, openai_embed
from lightrag.types import GPTKeywordExtractionFormat


def _get_base_url() -> str:
    """Return the base URL for the vLLM server."""
    return os.getenv("LLM_BINDING_HOST", "http://localhost:8000/v1")


async def vllm_model_complete(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, str]] | None = None,
    keyword_extraction: bool = False,
    **kwargs,
) -> str:
    """Call a vLLM server using the OpenAI-compatible API."""
    if history_messages is None:
        history_messages = []
    keyword_extraction = kwargs.pop("keyword_extraction", None)
    if keyword_extraction:
        kwargs["response_format"] = GPTKeywordExtractionFormat
    model_name = kwargs["hashing_kv"].global_config["llm_model_name"]
    return await openai_complete_if_cache(
        model_name,
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        base_url=_get_base_url(),
        api_key=kwargs.pop("api_key", None),
        **kwargs,
    )


async def vllm_embed(
    texts: list[str],
    embed_model: str,
    **kwargs,
):
    """Generate embeddings using the vLLM server's embedding endpoint."""
    return await openai_embed(
        texts,
        model=embed_model,
        base_url=_get_base_url(),
        api_key=kwargs.pop("api_key", None),
        client_configs=kwargs.pop("openai_client_configs", {}),
    )
