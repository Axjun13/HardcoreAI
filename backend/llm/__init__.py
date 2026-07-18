"""LLM provider clients for the HardcoreAI agent.

Re-exports the public surface of :mod:`llm.core` so callers can keep using
``import llm`` / ``llm.complete(...)`` / ``llm.PROVIDERS`` unchanged.
"""

from .core import (
    CompletionText,
    LLMError,
    PROVIDERS,
    available_providers,
    complete,
    context_window_for_model,
    context_window_for_provider,
    model_for_provider,
    stream,
)

__all__ = [
    "CompletionText",
    "LLMError",
    "PROVIDERS",
    "available_providers",
    "complete",
    "context_window_for_model",
    "context_window_for_provider",
    "model_for_provider",
    "stream",
]
