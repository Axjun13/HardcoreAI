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

Web-scraping extensions (search_web / ingest_url):
  - search_web(query)  → in-process web search (see rag/web_search.py): Brave
    API when BRAVE_API_KEY is set, else the key-less DuckDuckGo backend. No
    external server or port.
  - ingest_url(url)    → fetches the page with httpx, strips HTML, saves as a
    ``web__<slug>.txt`` file in data_dir, then re-indexes.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

CONTEXT_MARKER = "=== LLM-READY PROMPT CONTEXT WINDOW ==="

# fastembed model: small, fast, fully local ONNX (no torch). Override via env.
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# Chunking parameters (chars/tokens handled by LlamaIndex's SentenceSplitter).
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "64"))

# Name of the Chroma collection holding a user's chunks.
COLLECTION_NAME = "hardware_manuals"

# Prefix for filenames produced by ingest_url so the list endpoint can
# distinguish web-scraped documents from user-uploaded PDFs.
WEB_PREFIX = "web__"

# Maximum characters fetched per page before truncation (≈ 40 k tokens).
MAX_PAGE_CHARS = 200_000


class _TextExtractor(HTMLParser):
    """Minimal HTML-to-plaintext extractor using only stdlib html.parser.

    Skips <script>, <style>, <head> content. Collapses whitespace.
    Not a full sanitiser — good enough for extracting readable text from
    documentation and datasheet pages.
    """

    _SKIP_TAGS = {"script", "style", "head", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in self._SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in self._SKIP_TAGS and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        # Collapse runs of whitespace into a single space.
        return re.sub(r"[ \t]{2,}", " ", raw).strip()


def _html_to_text(html: str) -> str:
    """Extract readable text from an HTML string using only stdlib."""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


def _slug_url(url: str) -> str:
    """Convert a URL into a safe, deterministic filename stem.

    The result must be a **flat** filename (no slashes) safe on both
    Windows and Linux. All non-word characters, including path separators,
    are replaced with underscores.

    Example::
        https://www.st.com/resource/en/reference_manual/rm0090.pdf
        → st.com_resource_en_reference_manual_rm0090_pdf
    """
    parsed = urlparse(url)
    # netloc without leading www.
    host = re.sub(r"^www\.", "", parsed.netloc)
    # Replace every non-word character (including / and .) with _
    path = re.sub(r"[^\w]", "_", parsed.path).strip("_")
    slug = f"{host}_{path}" if path else host
    # Also sanitise the host portion (dots → underscores to keep it clean)
    slug = re.sub(r"[^\w]", "_", slug)
    # Truncate so the full filename (web__ + slug + .txt) stays under 200 chars.
    return slug[:180]


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
            allowed_extensions=_split_csv(os.getenv("ALLOWED_EXTENSIONS", ".pdf,.txt"), [".pdf", ".txt"]),
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
        embed_model: Any | None = None,
    ) -> None:
        self.config = config or RAGConfig.from_env()
        # Tests and offline deployments can inject any LlamaIndex-compatible
        # embedding model. Production keeps the lazy FastEmbed default.
        self._injected_embed_model = embed_model
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
            "embed_model": getattr(self._injected_embed_model, "model_name", EMBED_MODEL),
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

    # -- web-search / url-scrape -----------------------------------------

    def search_web(self, query: str, num_results: int = 5) -> list[dict]:
        """Run an in-process web search and return result metadata.

        Delegates to ``rag.web_search.search_web`` (Brave API when
        ``BRAVE_API_KEY`` is set, otherwise the key-less DuckDuckGo backend).

        Returns a list of dicts::

            [{"title": str, "url": str, "snippet": str}, ...]

        Never raises — returns a single-element list with an ``error`` key on
        failure so the agent tool can surface a readable message.
        """
        from .web_search import search_web as _search_web

        return _search_web(query, num_results=num_results)

    def ingest_url(self, url: str) -> dict:
        """Fetch *url*, extract plain text, and add it to the RAG index.

        The file is saved as ``web__<slug>.txt`` inside ``data_dir``.  If a
        file with that name already exists the call is a no-op (dedup).

        Returns::

            {
                "filename": str,
                "url": str,
                "size": int,        # bytes written (0 if skipped)
                "skipped": bool,    # True when the URL was already indexed
                "error": str | None,
            }
        """
        import httpx

        slug = _slug_url(url)
        filename = f"{WEB_PREFIX}{slug}.txt"
        dest = self.config.data_dir / filename

        if dest.exists():
            return {"filename": filename, "url": url, "size": 0, "skipped": True, "error": None}

        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "HardcoreAI-RAG/1.0 (+https://github.com/vardhin/HardcoreAI)"},
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type or "text/plain" in content_type:
                    raw_text = _html_to_text(resp.text) if "html" in content_type else resp.text
                else:
                    return {
                        "filename": filename,
                        "url": url,
                        "size": 0,
                        "skipped": False,
                        "error": f"Unsupported content-type: {content_type!r}",
                    }
        except Exception as exc:
            return {"filename": filename, "url": url, "size": 0, "skipped": False, "error": str(exc)}

        if not raw_text.strip():
            return {"filename": filename, "url": url, "size": 0, "skipped": False, "error": "Empty page text"}

        # Truncate very large pages to stay within token budget.
        if len(raw_text) > MAX_PAGE_CHARS:
            raw_text = raw_text[:MAX_PAGE_CHARS]

        # Prepend a source-URL header line so _build_index can surface it.
        body = f"# source: {url}\n\n{raw_text}"

        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        size = dest.stat().st_size

        try:
            # Only re-index the new file, not the entire corpus.
            self._build_index([dest])
        except Exception as exc:
            # The file is already on disk; report the indexing error but don't
            # delete the file — ingest() can pick it up on the next full run.
            return {"filename": filename, "url": url, "size": size, "skipped": False, "error": f"Index error: {exc}"}

        return {"filename": filename, "url": url, "size": size, "skipped": False, "error": None}

    # -- internals --------------------------------------------------------

    def _chroma_collection(self, *, create: bool):
        import chromadb

        self._chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self._chroma_dir))
        if create:
            return client, client.get_or_create_collection(COLLECTION_NAME)
        return client, client.get_collection(COLLECTION_NAME)

    def _build_index(self, files: list[Path]) -> int:
        """Index a list of files (PDFs and/or .txt) into Chroma.

        PDFs are loaded with LlamaIndex's PDFReader (preserves page metadata).
        Plain-text files (including web-scraped .txt) are loaded with
        SimpleDirectoryReader, which handles them natively without extra deps.
        """
        from llama_index.core import StorageContext, VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.readers.file import PDFReader
        from llama_index.vector_stores.chroma import ChromaVectorStore

        pdf_reader = PDFReader()
        documents = []
        for f in files:
            suffix = f.suffix.lower()
            if suffix == ".pdf":
                docs = pdf_reader.load_data(file=f)
                for d in docs:
                    d.metadata = {
                        **(d.metadata or {}),
                        "filename": f.name,
                        "source": "pdf",
                    }
            elif suffix == ".txt":
                # Read the raw text; strip the source-URL header line if present.
                raw = f.read_text(encoding="utf-8", errors="replace")
                # Extract optional source URL from first line (# source: <url>).
                source_url = ""
                lines = raw.splitlines()
                if lines and lines[0].startswith("# source: "):
                    source_url = lines[0][len("# source: "):].strip()
                    raw = "\n".join(lines[1:]).strip()
                from llama_index.core import Document
                docs = [Document(
                    text=raw,
                    metadata={
                        "filename": f.name,
                        "source": "web",
                        "source_url": source_url,
                    },
                )]
            else:
                # Unknown extension — skip gracefully.
                continue
            documents.extend(docs)

        if not documents:
            return 0

        _, collection = self._chroma_collection(create=True)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

        VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=self._embedding_model(),
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
            vector_store, embed_model=self._embedding_model()
        )
        retriever = index.as_retriever(similarity_top_k=top_k)
        return retriever.retrieve(query)

    def _embedding_model(self):
        return self._injected_embed_model or _get_embed_model()

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
