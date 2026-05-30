"""Contract tests for the RAG engine (now a Python-native in-process service).

The RAG service used to shell out to a Go ``rag-cli`` binary; it is now a Python
engine (LlamaIndex + Chroma + fastembed) consumed directly by the backend
(api/routers/rag.py, agent/tools.py). The CLI surface is gone, so these tests
assert the *in-process contract* the backend actually depends on:

  RAGService(config=...) / .config.db_path / .config.data_dir
  .ingest()  -> dict(returncode=0, ...) and a persistent store on disk
  .query(q, k=, max_tokens=) -> dict with:
        returncode == 0
        stdout containing "=== LLM-READY PROMPT CONTEXT WINDOW ==="
        a non-empty "context" block (what agent/tools.py forwards to the LLM)
  query against an uninitialised store -> returncode != 0, stderr signals the
        missing store (agent checks for "no such table: chunks")

These assert on the contract (return shape + stdout marker + extractable
context), not on which chunks rank where.
"""

from __future__ import annotations

# The marker the agent (and RAGService._extract_context) split on.
CONTEXT_MARKER = "=== LLM-READY PROMPT CONTEXT WINDOW ==="


def test_ingest_populates_store(rag_db):
    # The rag_db fixture runs ingest() and asserts the store file exists; reaching
    # here means ingest exited 0 and produced a persistent store.
    assert rag_db.exists()
    assert rag_db.stat().st_size > 0


def test_query_missing_store_fails_gracefully(rag_service_cls, tmp_path):
    """A query before any ingest must not crash: non-zero result, and stderr
    carries the signal agent/tools.py checks for."""
    from rag import RAGConfig

    cfg = RAGConfig.from_env()
    cfg.data_dir = tmp_path / "documents"
    cfg.db_path = tmp_path / "chroma" / "chroma.sqlite3"
    svc = rag_service_cls(config=cfg)
    svc._chroma_dir = tmp_path / "chroma"

    result = svc.query("anything", k=3, max_tokens=1500)
    assert result["returncode"] != 0
    assert "no such table: chunks" in result["stderr"]


def test_query_emits_context_marker(rag_query):
    """The load-bearing contract: query stdout contains the marker the backend
    splits on, and the call succeeds."""
    result = rag_query("What causes a BusFault?", k=3, max_tokens=1500)
    assert result["returncode"] == 0, result["stderr"]
    assert CONTEXT_MARKER in result["stdout"]


def test_query_context_block_is_extractable(rag_query):
    """Mirror RAGService._extract_context: text after the marker is non-empty,
    and the pre-extracted `context` field the backend forwards is also non-empty."""
    result = rag_query("GPIO output configuration", k=3, max_tokens=1500)
    assert result["returncode"] == 0, result["stderr"]
    assert CONTEXT_MARKER in result["stdout"]

    _, context_block = result["stdout"].split(CONTEXT_MARKER, 1)
    assert context_block.strip(), "context block after marker should not be empty"

    # The field agent/tools.py actually reads.
    assert isinstance(result["context"], str)
    assert result["context"].strip(), "extracted context should not be empty"
