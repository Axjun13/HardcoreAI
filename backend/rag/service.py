"""Python-native RAG engine for HardcoreAI.

Provides hardware-manual context to the LLM agent in the IDE backend. This was
previously a thin wrapper that shelled out to a Go ``rag-cli`` binary; it is now
a fully in-process Python engine built on LlamaIndex + Chroma + fastembed
(ONNX, no torch). Embeddings are local and offline after the model is cached.

The public surface is kept compatible with the previous subprocess-based
implementation so callers (api/routers/rag.py, agent/tools.py) need no changes:

  RAGService(user_id=, project_id=)
  .config.data_dir / .config.db_path   (Paths; routes call .exists()/.iterdir())
  .stage_documents(iterable) -> list[str]
  .ingest() -> dict
  .query(text, k=, max_tokens=) -> dict   (dict has returncode/stderr/stdout/context)

``query`` output still contains the marker the agent splits on:

    === LLM-READY PROMPT CONTEXT WINDOW ===
"""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CONTEXT_MARKER = "=== LLM-READY PROMPT CONTEXT WINDOW ==="

# fastembed model: small, fast, fully local ONNX (no torch). Override via env.
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# Chunking parameters (chars/tokens handled by LlamaIndex's SentenceSplitter).
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "64"))

# Name of the Chroma collection holding a user's chunks.
COLLECTION_NAME = "hardware_manuals"


def _split_csv(raw: str, default: list[str]) -> list[str]:
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return values or default


@dataclass(slots=True)
class RAGConfig:
    db_path: Path
    data_dir: Path
    upload_dir: Path
    default_k: int
    default_max_tokens: int
    allowed_extensions: list[str]
    max_upload_size_mb: int

    @classmethod
    def from_env(cls) -> "RAGConfig":
        return cls(
            db_path=Path(os.getenv("RAG_DB_PATH", "data/rag.db")),
            data_dir=Path(os.getenv("RAG_DATA_DIR", "data")),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "integration/uploads")),
            default_k=int(os.getenv("RAG_K", "3")),
            default_max_tokens=int(os.getenv("RAG_MAX_TOKENS", "3000")),
            allowed_extensions=_split_csv(os.getenv("ALLOWED_EXTENSIONS", ".pdf"), [".pdf"]),
            max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")),
        )


# The embedding model is process-global and lazily loaded once: constructing it
# downloads/loads the ONNX weights, which is expensive to repeat per request.
_embed_lock = threading.Lock()
_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                from llama_index.embeddings.fastembed import FastEmbedEmbedding

                _embed_model = FastEmbedEmbedding(model_name=EMBED_MODEL)
    return _embed_model


class RAGService:
    def __init__(
        self,
        config: RAGConfig | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        self.config = config or RAGConfig.from_env()
        if user_id:
            base = Path("data/users") / str(user_id)
            # Chroma persists into a directory; db_path points at the sqlite file
            # Chroma actually creates there, so route checks (.exists()/.unlink())
            # keep working unchanged.
            self._chroma_dir = base / "chroma"
            self.config.db_path = self._chroma_dir / "chroma.sqlite3"
            self.config.data_dir = base / "documents"
            self.config.upload_dir = base / "uploads"
        else:
            self._chroma_dir = self.config.db_path.parent

    # -- public API -------------------------------------------------------

    def health_check(self) -> dict[str, object]:
        return {
            "ok": True,
            "db_exists": self.config.db_path.exists(),
            "data_dir_exists": self.config.data_dir.exists(),
            "rag_db_path": str(self.config.db_path),
            "rag_data_dir": str(self.config.data_dir),
            "upload_dir": str(self.config.upload_dir),
            "embed_model": EMBED_MODEL,
        }

    def query(
        self,
        query: str,
        chip_family: str = "",
        k: int | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, object]:
        top_k = k or self.config.default_k
        budget = max_tokens or self.config.default_max_tokens

        if not self.config.db_path.exists():
            # Mirror the old "no such table: chunks" signal the agent checks for.
            return self._result(
                stdout="",
                stderr="no such table: chunks",
                returncode=1,
            )

        try:
            nodes = self._retrieve(query, top_k, chip_family)
        except Exception as exc:  # surface as a non-zero "process" result
            return self._result(stdout="", stderr=str(exc), returncode=1)

        stdout = self._render_stdout(query, chip_family, top_k, budget, nodes)
        return self._result(stdout=stdout, stderr="", returncode=0)

    def ingest(
        self,
        data_dir: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> dict[str, object]:
        target_dir = Path(data_dir) if data_dir else self.config.data_dir
        if db_path:
            self.config.db_path = Path(db_path)
            self._chroma_dir = self.config.db_path.parent

        pdfs = sorted(
            p for p in target_dir.glob("*")
            if p.is_file() and p.suffix.lower() in self.config.allowed_extensions
        ) if target_dir.exists() else []

        if not pdfs:
            return self._result(
                stdout=f"No documents found in directory: {target_dir}",
                stderr="",
                returncode=0,
            )

        try:
            count = self._build_index(pdfs)
        except Exception as exc:
            return self._result(stdout="", stderr=str(exc), returncode=1)

        return self._result(
            stdout=f"INGESTION COMPLETE\nIndexed {count} chunks from {len(pdfs)} file(s).",
            stderr="",
            returncode=0,
        )

    def stage_documents(self, files: Iterable[Path]) -> list[str]:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for file_path in files:
            file_path = Path(file_path)
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in self.config.allowed_extensions:
                raise ValueError(f"Unsupported file type: {file_path.name}")
            destination = self.config.data_dir / file_path.name
            shutil.copy2(file_path, destination)
            copied.append(str(destination))
        return copied

    # -- internals --------------------------------------------------------

    def _chroma_collection(self, *, create: bool):
        import chromadb

        self._chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self._chroma_dir))
        if create:
            return client, client.get_or_create_collection(COLLECTION_NAME)
        return client, client.get_collection(COLLECTION_NAME)

    def _build_index(self, pdfs: list[Path]) -> int:
        from llama_index.core import StorageContext, VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.readers.file import PDFReader
        from llama_index.vector_stores.chroma import ChromaVectorStore

        reader = PDFReader()
        documents = []
        for pdf in pdfs:
            docs = reader.load_data(file=pdf)
            for d in docs:
                d.metadata = {**(d.metadata or {}), "filename": pdf.name}
            documents.extend(docs)

        _, collection = self._chroma_collection(create=True)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

        VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=_get_embed_model(),
            transformations=[splitter],
            show_progress=False,
        )
        return collection.count()

    def _retrieve(self, query: str, top_k: int, chip_family: str):
        from llama_index.core import VectorStoreIndex
        from llama_index.vector_stores.chroma import ChromaVectorStore

        _, collection = self._chroma_collection(create=False)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        index = VectorStoreIndex.from_vector_store(
            vector_store, embed_model=_get_embed_model()
        )
        retriever = index.as_retriever(similarity_top_k=top_k)
        return retriever.retrieve(query)

    # -- output formatting ------------------------------------------------

    def _render_stdout(self, query, chip_family, top_k, budget, nodes) -> str:
        lines: list[str] = []
        lines.append(f"Running hybrid retrieval for: {query!r}")
        lines.append(f"Options: ChipFamily={chip_family}, K={top_k}, MaxTokens={budget}")
        lines.append("")
        lines.append("=== RANKED SEARCH RESULTS ===")
        for i, node in enumerate(nodes, start=1):
            meta = node.node.metadata or {}
            filename = meta.get("filename", meta.get("file_name", "unknown"))
            page = meta.get("page_label", meta.get("page_number", "N/A"))
            score = node.score if node.score is not None else 0.0
            snippet = node.node.get_content().strip().replace("\n", " ")[:120]
            lines.append(f"Rank {i} (Score: {score:.4f})")
            lines.append(f"  - File: {filename} (Page {page})")
            lines.append(f'  - Snippet: "{snippet}..."')
        lines.append("")

        context, used, dropped = self._build_context(nodes, budget)
        lines.append(CONTEXT_MARKER)
        lines.append(f"Used Chunks: {used} | Trimmed Chunks: {dropped}")
        lines.append("-" * 70)
        lines.append(context)
        lines.append("-" * 70)
        return "\n".join(lines)

    def _build_context(self, nodes, budget: int) -> tuple[str, int, int]:
        """Assemble formatted chunks under a token budget (approx 4 chars/token)."""
        char_budget = max(budget, 1) * 4
        blocks: list[str] = []
        used = 0
        running = 0
        for node in nodes:
            block = self._format_node(node)
            if running + len(block) > char_budget and used > 0:
                break
            blocks.append(block)
            running += len(block)
            used += 1
        dropped = len(nodes) - used
        return "\n".join(blocks).strip(), used, dropped

    @staticmethod
    def _format_node(node) -> str:
        meta = node.node.metadata or {}
        filename = meta.get("filename", meta.get("file_name", "unknown"))
        page = meta.get("page_label", meta.get("page_number", "N/A"))
        text = node.node.get_content().strip()
        return (
            f"[Source: {filename} | doc_type: reference_manual]\n"
            f"Page: {page}\n\n"
            f"{text}\n\n---\n"
        )

    @staticmethod
    def _result(stdout: str, stderr: str, returncode: int) -> dict[str, object]:
        return {
            "context": RAGService._extract_context(stdout),
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    @staticmethod
    def _extract_context(stdout: str | None) -> str:
        if not stdout:
            return ""
        if CONTEXT_MARKER not in stdout:
            return stdout.strip()
        _, context_block = stdout.split(CONTEXT_MARKER, 1)
        lines = [line.rstrip() for line in context_block.splitlines()]
        trimmed = [line for line in lines if line.strip("- ").strip()]
        return "\n".join(trimmed).strip()
