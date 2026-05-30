"""The HardcoreAI agent package.

A C-style THINK/CALL tool-calling loop over the workbench. The public surface
the API layer needs:

  - ``run_agent_phase`` — orchestrates one conversational agent run (solver).
  - ``AgentTrace``      — the run record returned to the frontend (parser).
"""

from .parser import AgentTrace, run_phase
from .solver import run_agent_phase

__all__ = ["AgentTrace", "run_phase", "run_agent_phase"]
