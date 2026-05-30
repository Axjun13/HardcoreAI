"""Shared fixtures for the Go-service contract tests.

These fixtures build the current implementation of each service and boot it so the
tests can drive it as a black box. The tests assert on the *contract* (HTTP shape,
status codes, CLI stdout markers, exit codes) — not internal behavior — so the same
suite can later run against the Python reimplementation unchanged.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

# The emulator service is now Python-native (backend/emulator), with its
# firmware bundled alongside it so the service is self-contained.
FIRMWARE_ELF = BACKEND_DIR / "emulator/Blinky/.pio/build/genericSTM32F405RG/firmware.elf"

# Test ports kept distinct from the production 62019 so a running dev server
# does not collide with the suite.
EMULATOR_TEST_PORT = 62029


def _free_port_or(default: int) -> int:
    """Return `default` if it is free, otherwise an ephemeral free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", default))
            return default
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _kill_qemu() -> None:
    """Best-effort cleanup of QEMU processes the emulator may have spawned."""
    for name in ("qemu-system-arm",):
        subprocess.run(["killall", name], capture_output=True)


# ---------------------------------------------------------------------------
# Capability flags — used by tests to skip gracefully on a partial toolchain.
# ---------------------------------------------------------------------------

HAS_QEMU = _have("qemu-system-arm")
HAS_ARM_GDB = _have("arm-none-eabi-gdb")
HAS_PIO = _have("pio") or (Path.home() / ".platformio/penv/bin/pio").exists()
HAS_FIRMWARE = FIRMWARE_ELF.exists()


# ---------------------------------------------------------------------------
# Emulator service fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def emulator() -> str:
    """Boot the Python FastAPI emulator service and yield its base URL.

    Run with the backend venv so fastapi/uvicorn/pygdbmi resolve, and with
    import root = backend/ so `emulator.app` is importable. The service resolves
    its bundled firmware relative to its own package, so CWD is irrelevant.
    """
    py = BACKEND_DIR / ".venv/bin/python"
    if not py.exists():
        pytest.skip("backend venv not found (backend/.venv)")
    port = _free_port_or(EMULATOR_TEST_PORT)
    env = {**os.environ, "EMULATOR_HOST": "127.0.0.1", "EMULATOR_PORT": str(port)}
    proc = subprocess.Popen(
        [str(py), "-m", "emulator.app"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"

    # Wait for the server to accept connections.
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=1.0)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.terminate()
        out = proc.stdout.read() if proc.stdout else ""
        pytest.fail(f"emulator did not come up on {base_url}\n{out}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    _kill_qemu()


@pytest.fixture
def client(emulator) -> httpx.Client:
    with httpx.Client(base_url=emulator, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# RAG fixtures (Python-native engine: LlamaIndex + Chroma + fastembed)
#
# The RAG service is no longer a CLI; it's an in-process Python engine consumed
# directly by the backend. These fixtures import RAGService from backend/rag and
# drive it as a black box. The contract under test is unchanged: query() output
# must contain the "=== LLM-READY PROMPT CONTEXT WINDOW ===" marker and a
# non-empty context block, ingest() must populate a persistent store, and a query
# against an uninitialised store must fail gracefully.
# ---------------------------------------------------------------------------

BACKEND_DIR = REPO_ROOT / "backend"
# Bundled corpus now lives in the backend so it survives Go-tree deletion.
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
    cfg = RAGConfig.from_env()
    cfg.data_dir = work / "documents"
    cfg.upload_dir = work / "uploads"
    cfg.db_path = work / "chroma" / "chroma.sqlite3"
    svc = RAGService(config=cfg)
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
