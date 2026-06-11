"""MCP server exposing the Ultima IV agent environment.

This wraps `ultima4.env.UltimaEnv` (the stable observe/act contract over the headless game)
as a `Model Context Protocol <https://modelcontextprotocol.io>`_ server, so any MCP-capable
LLM agent can play Ultima IV by calling tools instead of reading a CLI transcript.

One process holds a single live game session (a module-level `UltimaEnv`). Every tool returns
the JSON-serializable observation dict from the env (see `UltimaEnv.observe`).

Action grammar (quoted from `ultima4.env.UltimaEnv.act`)::

    "move N" | "move S" | "move E" | "move W"   # walk / pick a direction the game asked for
    "key <LETTER>"                              # a command letter: T(alk) E(nter) C(ast)
                                                #   Z(tats) K(limb) D(escend) A(ttack) ...
    "say <text>"                               # type into an active Talk/shop interaction
    "pass"                                      # wait one turn (SPACE)

Always read `observe()["legal_actions"]` before acting — it lists exactly which actions are
valid in the current state, so the agent never has to guess.

Run it (stdio transport)::

    /home/ein/projects/ultimate_rewrite/u4py/.venv/bin/python -m ultima4.agent.mcp_server

The `mcp` package is imported lazily so that merely importing this module (e.g. when the test
suite imports the `ultima4` package) never fails if `mcp` is not installed — the helpful error
is raised only when you actually try to build/run the server.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..env import UltimaEnv

# --- single live session -----------------------------------------------------
_DEFAULT_SEED = 7
_env = UltimaEnv(seed=_DEFAULT_SEED)


# --- plain tool logic (transport-agnostic; unit-testable without a client) ----
# The FastMCP @mcp.tool() wrappers below delegate to these, so tests can call the logic
# directly without standing up a stdio transport.
def new_game(seed: int = _DEFAULT_SEED) -> Dict[str, Any]:
    """Start a fresh, deterministic game from `seed` and return the opening observation."""
    return _env.reset(seed=seed)


def observe() -> Dict[str, Any]:
    """Return the current observation (does not advance the game)."""
    return _env.observe()


def act(action: str) -> Dict[str, Any]:
    """Apply ONE action string and return the resulting observation.

    Grammar: 'move N|S|E|W' | 'key <LETTER>' | 'say <text>' | 'pass'. An unknown or malformed
    action is reported in the returned observation's `error` field rather than raising.
    """
    return _env.act(action)


def legal_actions() -> List[str]:
    """Return the list of action strings that are legal in the current game state."""
    return _env.legal_actions()


def play(actions: List[str]) -> Dict[str, Any]:
    """Apply several actions in order; return the observation after the LAST one.

    With no actions, returns the current observation. Use `act` if you need the observation
    after every step.
    """
    trace = _env.play(actions)
    return trace[-1] if trace else _env.observe()


def list_demos() -> List[Dict[str, Any]]:
    """List the named live-demo scenarios (scripted playthroughs of notable game moments)."""
    from ..demo_scenarios import SCENARIOS
    return [{"name": name, "desc": spec["desc"], "tags": spec["tags"]}
            for name, spec in SCENARIOS.items()]


def run_demo(name: str, seed: int = _DEFAULT_SEED) -> Dict[str, Any]:
    """Run a named demo scenario and return its transcript and pass/fail result.

    Use `list_demos` for the available names. This runs an independent scripted game and does
    NOT affect the live session driven by `act`/`observe`.
    """
    from ..demo_scenarios import run
    d = run(name, seed=seed)
    return {"name": name, "seed": seed, "passed": d.passed,
            "failures": list(d.failures), "transcript": d.transcript()}


# --- FastMCP server ----------------------------------------------------------
def build_server():
    """Construct and return the FastMCP server with all tools registered.

    Imported lazily so importing this module never requires `mcp` to be installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - exercised only when mcp is absent
        raise RuntimeError(
            "The 'mcp' package is required to run the Ultima IV MCP server. "
            "Install it into the project venv:\n"
            "    u4py/.venv/bin/python -m pip install mcp"
        ) from e

    mcp = FastMCP(
        "ultima4",
        instructions=(
            "Play a faithful Ultima IV port. Call observe() to perceive the world, then act() "
            "with one action string. Action grammar: 'move N|S|E|W', 'key <LETTER>' (a command "
            "letter like T=talk, E=enter, C=cast, Z=ztats, K=klimb, D=descend, A=attack), "
            "'say <text>' (into an active Talk/shop interaction), or 'pass' (wait a turn). "
            "ALWAYS consult observe()['legal_actions'] first — it lists exactly which actions "
            "are valid right now. new_game(seed) restarts deterministically."
        ),
    )

    # Register the plain functions as tools (descriptions come from their docstrings).
    mcp.tool()(new_game)
    mcp.tool()(observe)
    mcp.tool()(act)
    mcp.tool()(legal_actions)
    mcp.tool()(play)
    mcp.tool()(list_demos)
    mcp.tool()(run_demo)
    return mcp


def main() -> None:
    """Stdio entrypoint: build the server and serve over stdio (FastMCP default)."""
    build_server().run()


if __name__ == "__main__":
    main()
