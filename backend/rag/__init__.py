"""RAG service for HardcoreAI.

Re-exports :class:`RAGService` and :class:`RAGConfig` so callers can use
``from rag import RAGService`` unchanged.
"""

from .service import RAGConfig, RAGService

__all__ = ["RAGConfig", "RAGService"]
