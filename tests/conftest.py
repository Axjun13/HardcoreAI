"""Shared fixtures for the service contract tests.

These fixtures build the current implementation of each service and drive it as a
black box. The tests assert on the *contract* (output shape, status codes,
markers) — not internal behavior — so the same suite can run against alternate
reimplementations unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"


# ---------------------------------------------------------------------------
# RAG fixtures (Python-native engine: LlamaIndex + Chroma + fastembed)
#
# The RAG service is an in-process Python engine consumed directly by the
# backend. These fixtures import RAGService from backend/rag and drive it as a
# black box. The contract under test: query() output must contain the
# "=== LLM-READY PROMPT CONTEXT WINDOW ===" marker and a non-empty context
# block, ingest() must populate a persistent store, and a query against an
# uninitialised store must fail gracefully.
# ---------------------------------------------------------------------------

# Bundled corpus lives in the backend so it survives Go-tree deletion.
RAG_CORPUS_PDF = BACKEND_DIR / "rag" / "corpus" / "rm0090.pdf"


def _import_rag_service():
    """Import RAGService/RAGConfig from the backend package (import root = backend/)."""
    import sys

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from rag import RAGConfig, RAGService  # noqa: WPS433 (runtime import by design)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"backend rag package not importable: {exc}")
    return RAGService, RAGConfig


@pytest.fixture(scope="session")
def rag_service_cls():
    """The RAGService class, imported once per session."""
    RAGService, _ = _import_rag_service()
    return RAGService


def _make_service(work: Path):
    """Construct a RAGService pointed at an isolated temp store + corpus dir."""
    RAGService, RAGConfig = _import_rag_service()
    from llama_index.core.embeddings import MockEmbedding

    cfg = RAGConfig.from_env()
    cfg.data_dir = work / "documents"
    cfg.upload_dir = work / "uploads"
    cfg.db_path = work / "chroma" / "chroma.sqlite3"
    # These tests verify persistence/retrieval/output shape, not one hosted
    # embedding model's ranking quality. Keep the contract suite offline.
    svc = RAGService(config=cfg, embed_model=MockEmbedding(embed_dim=384))
    svc._chroma_dir = work / "chroma"
    return svc


@pytest.fixture(scope="session")
def rag_ingested_service(tmp_path_factory):
    """Ingest the bundled rm0090.pdf once into a temp store, shared by query tests.

    A slice of the (large) reference manual is used to keep ingestion fast while
    still exercising real PDF parsing, chunking, and embedding. Yields the
    ingested RAGService instance."""
    if not RAG_CORPUS_PDF.exists():
        pytest.skip("rm0090.pdf corpus not present in backend/rag/corpus/")

    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"pypdf not available to build corpus slice: {exc}")

    work = tmp_path_factory.mktemp("ragdb")
    docs_dir = work / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Take a slice of pages so ingestion stays well under the test timeout.
    src = PdfReader(str(RAG_CORPUS_PDF))
    writer = PdfWriter()
    for page in src.pages[200:215]:
        writer.add_page(page)
    with open(docs_dir / "rm0090_slice.pdf", "wb") as fh:
        writer.write(fh)

    svc = _make_service(work)
    result = svc.ingest()
    if result["returncode"] != 0 or not svc.config.db_path.exists():
        pytest.fail(f"ingest failed:\n{result['stdout']}\n{result['stderr']}")
    return svc


@pytest.fixture
def rag_db(rag_ingested_service) -> Path:
    """Path to the persistent store file the backend checks with .exists()."""
    return rag_ingested_service.config.db_path


@pytest.fixture
def rag_query(rag_ingested_service):
    """Return a callable that runs query() against the shared ingested store."""
    return rag_ingested_service.query
