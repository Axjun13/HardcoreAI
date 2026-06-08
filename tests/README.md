# Characterization / contract test suite

These tests lock down the **observable behavior** of the components the Python
backend depends on. They began life as a regression gate for the **Go → Python
port** (the Go services are now deleted), and remain the contract gate for the
Python implementations:

- **RAG engine** (`backend/rag/`) — an in-process Python library (LlamaIndex +
  Chroma + fastembed) consumed directly by the backend; no longer a CLI.
- **Agent** (`backend/agent/`) — the solver/toolbox the backend exposes over its
  agent endpoints.

These tests treat each component as a black box and assert on the *contract* the
backend actually consumes (for RAG the query() output markers and
persistent-store behavior) — not on internal details.

> We deliberately do **not** assert on internal details (chunk boundaries, exact
> rerank scores). Those are implementation details a correct implementation may
> legitimately differ on. We assert on the *contract*: output shape, markers.

## Layout

```text
tests/
  conftest.py            # shared fixtures: drives the RAG engine
  test_agent_contract.py
  test_rag_contract.py
  README.md
```

## Prerequisites (already installed on the dev machine)

- The **backend venv** (`backend/.venv`), which carries llama-index/chroma/
  fastembed for the RAG engine.

## Running

The suite needs the backend's dependencies (RAG libs), so run it with the
**backend venv**:

```bash
# from repo root
backend/.venv/bin/python -m pytest tests/ -v

# just the agent contract
backend/.venv/bin/python -m pytest tests/test_agent_contract.py -v

# just the rag contract
backend/.venv/bin/python -m pytest tests/test_rag_contract.py -v
```

Tests that require a dependency which is absent **skip** with a clear reason
rather than failing, so the suite is honest on a partially provisioned machine.
