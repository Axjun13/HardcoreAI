"""LLM provider clients for the HardcoreAI agent.

Re-exports the public surface of :mod:`llm.core` so callers can keep using
``import llm`` / ``llm.complete(...)`` / ``llm.PROVIDERS`` unchanged.
"""

from .core import (
    LLMError,
    PROVIDERS,
    available_providers,
    complete,
)

__all__ = ["LLMError", "PROVIDERS", "available_providers", "complete"]
