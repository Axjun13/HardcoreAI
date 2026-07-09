from __future__ import annotations

import importlib.util
from pathlib import Path

_module_path = Path(__file__).resolve().parent.parent.parent / "agent" / "board_context.py"
_spec = importlib.util.spec_from_file_location("backend_agent_board_context", _module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load board context module from {_module_path}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

globals().update({name: getattr(_module, name) for name in dir(_module) if not name.startswith("__")})
__all__ = [name for name in globals() if not name.startswith("__")]
