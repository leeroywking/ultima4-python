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

from typing import Any, Callable, Dict, List

from ..env import UltimaEnv

# --- single live session -----------------------------------------------------
_DEFAULT_SEED = 7
_env = UltimaEnv(seed=_DEFAULT_SEED)

# Optional visible window mirroring THIS session (see `serve_windowed`). When attached, every
# state-changing tool (act/new_game/play) is applied ON the window's render thread so a human
# watching the window sees each move land. When None, the tools mutate `_env` directly (headless).
_window = None  # type: Any
_viewer_note = ("Headless: no on-screen game window is attached — the human sees play only as the "
                "inline observations returned by these tools. The shipped .mcp.json launches with "
                "--window, so a window normally appears whenever the server's machine has a display; "
                "if there's none, either no display was detected or the server was launched without "
                "--window. Switching requires relaunching the server with --window and RESTARTING "
                "Claude Code so it reconnects — it cannot be toggled mid-session.")


def attach_window(window) -> None:
    global _window
    _window = window


def detach_window() -> None:
    global _window
    _window = None


def viewer_status() -> Dict[str, Any]:
    """Report whether a live game WINDOW is mirroring this session for a human to watch.

    Call this if the human asks to *see* the game / a window, or wonders why there's no window.
    Returns {window_attached, mode, note}. If `window_attached` is false, relay the `note`: play is
    headless (visible only as inline observations), and getting an on-screen window needs an --window
    relaunch + a Claude Code restart — it can't be turned on mid-session."""
    attached = _window is not None
    return {
        "window_attached": attached,
        "mode": "windowed" if attached else "headless",
        "note": ("A game window is open and mirrors each of your moves live." if attached
                 else _viewer_note),
    }


def _apply(fn: Callable[[], Any], label: str = None) -> Any:
    """Run a one-shot (single-turn) state change on the window's render thread if one is attached
    (so it's visible and race-free), else run it inline. Falls back to inline if the window stopped."""
    w = _window
    if w is not None:
        try:
            return w.submit(fn, label=label)
        except Exception:
            pass   # window gone/timed out — degrade to headless rather than fail the tool
    return fn()


def _apply_op(make_gen: Callable[[], Any], label: str = None) -> Any:
    """Run a multi-turn op (a generator factory: travel/wait/play) — ANIMATED on the render thread
    one turn per frame if a window is attached, else driven to completion inline. Returns the
    generator's final value."""
    w = _window
    if w is not None:
        try:
            return w.submit_op(make_gen(), label=label)
        except Exception:
            return _env.observe()   # window gone/timed out — don't re-drive (would double-apply)
    gen = make_gen()
    try:
        while True:
            next(gen)
    except StopIteration as e:
        return e.value


# --- plain tool logic (transport-agnostic; unit-testable without a client) ----
# The FastMCP @mcp.tool() wrappers below delegate to these, so tests can call the logic
# directly without standing up a stdio transport.
def new_game(seed: int = _DEFAULT_SEED) -> Dict[str, Any]:
    """Start a fresh, deterministic game from `seed` and return the opening observation."""
    return _apply(lambda: _env.reset(seed=seed), label=f"new_game({seed})")


def observe() -> Dict[str, Any]:
    """Return the current observation (does not advance the game)."""
    return _env.observe()


def act(action: str) -> Dict[str, Any]:
    """Apply ONE action string and return the resulting observation.

    Grammar: 'move N|S|E|W' | 'key <LETTER>' | 'say <text>' | 'pass'. An unknown or malformed
    action is reported in the returned observation's `error` field rather than raising.
    """
    return _apply(lambda: _env.act(action), label=action)


def legal_actions() -> List[str]:
    """Return the list of action strings that are legal in the current game state."""
    return _env.legal_actions()


def set_verbosity(mode: str = "min") -> Dict[str, Any]:
    """Control how much state each observation carries — set 'min' up front to save tokens on long
    playthroughs. In 'min', an observation OMITS the party / gold / food / inventory / items /
    legal_actions blocks on turns where they didn't change since the last observation (omitted ==
    unchanged); position / mode / messages / moons / combat are always present. 'full' (default)
    sends everything every turn. The returned observation re-sends everything once."""
    _env.verbosity = "min" if str(mode).lower().startswith("min") else "full"
    _env._min_prev = {}
    return observe()


def wait(seconds: float) -> Dict[str, Any]:
    """Let `seconds` of real game-time pass on the moon clock, then return the observation.

    The moons run on a real-time clock, independent of your moves — `wait` is how you let that
    clock advance without moving (e.g. to wait for a moongate to cycle into reach). `observe()`
    reports the current phases and any open gate under `moons`."""
    return _apply_op(lambda: _env.wait_steps(seconds), label=f"wait {seconds}s")


def wait_until(condition: str) -> Dict[str, Any]:
    """Advance the moon clock until a condition holds, then return the observation.

    Conditions: 'moongate' (an open gate is on/adjacent to you), 'moons_dark' (both moons new —
    for harvesting mandrake/nightshade), 'trammel N', or 'felucca N'. The observation gains
    `wait_reason` and `waited_seconds`."""
    return _apply_op(lambda: _env.wait_until_steps(condition), label=f"wait_until {condition}")


def travel_to(x: int, y: int, max_steps: int = 100) -> Dict[str, Any]:
    """Walk toward tile (x, y) over many turns in ONE call — use this instead of dozens of single
    `move` calls when crossing open terrain. It pathfinds around obstacles (respecting your
    transport) and takes real turns, but STOPS early and returns the observation the moment
    anything interesting happens: arrival, combat, a dialog opening, taking damage, a block, or
    `max_steps`. The result carries `travel_reason` and `steps_taken`. Overworld and towns only."""
    return _apply_op(lambda: _env.travel_steps(x, y, max_steps), label=f"travel_to({x},{y})")


def play(actions: List[str]) -> Dict[str, Any]:
    """Apply several actions in order; return the observation after the LAST one.

    With no actions, returns the current observation. Use `act` if you need the observation
    after every step.
    """
    if not actions:
        return observe()
    return _apply_op(lambda: _env.play_steps(actions), label=f"play({len(actions)} actions)")


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
            "are valid right now. new_game(seed) restarts deterministically. "
            "Prefer the batch tools over spamming single steps: to cross open terrain call "
            "travel_to(x, y) (it walks the whole path in one call and stops on anything "
            "interesting); to let the real-time moons advance (e.g. for a moongate) call "
            "wait(seconds) or wait_until('moongate'/'moons_dark'/'trammel N'/'felucca N') instead "
            "of repeating pass. Check observe()['moons'] to plan moongate travel. "
            "To save tokens on long playthroughs, call set_verbosity('min') once at the start "
            "(observations then omit unchanged party/inventory/legal_actions). Cite the precomputed "
            "moongate + companion/town/join tables in docs/AGENTS.md instead of re-deriving them."
        ),
    )

    # Register the plain functions as tools (descriptions come from their docstrings).
    mcp.tool()(new_game)
    mcp.tool()(observe)
    mcp.tool()(act)
    mcp.tool()(legal_actions)
    mcp.tool()(set_verbosity)
    mcp.tool()(play)
    mcp.tool()(wait)
    mcp.tool()(wait_until)
    mcp.tool()(travel_to)
    mcp.tool()(viewer_status)
    mcp.tool()(list_demos)
    mcp.tool()(run_demo)
    return mcp


def serve_windowed(which: str = "ega", action_every: int = 6) -> None:
    """Serve the MCP stdio protocol AND mirror this session in a visible, human-watchable window.

    The MCP server runs on the MAIN thread exactly as usual (so its stdio/signal behavior is
    unchanged); a `LiveWindow` runs on a background thread and every `act`/`new_game`/`play` is
    applied on that render thread (via `attach_window`), so the human watches the agent's moves
    land live. If no display is available, we log to stderr and fall back to a headless server.
    """
    import sys
    import threading
    from ..live_window import LiveWindow

    ready = threading.Event()
    state: Dict[str, Any] = {}

    def window_thread():
        try:
            win = LiveWindow(_env, which=which, action_every=action_every)
        except Exception as e:                      # no display, bad driver, etc.
            state["error"] = e
            ready.set()
            return
        state["window"] = win
        attach_window(win)
        ready.set()
        try:
            win.run()                                # blocks here until the window is closed
        finally:
            detach_window()
            win.close()

    t = threading.Thread(target=window_thread, name="ultima4-window", daemon=True)
    t.start()
    ready.wait(timeout=15)
    if "error" in state:
        global _viewer_note
        _viewer_note = (f"Headless: tried to open a game window but no usable display was found "
                        f"({state['error']!r}), so play is visible only as inline observations. To "
                        f"watch on screen, run the server on a machine with a display and RESTART "
                        f"Claude Code. (viewer_status reflects this.)")
        print(f"[mcp --window] could not open a game window ({state['error']!r}); "
              f"serving headless. Set SDL_VIDEODRIVER=dummy to silence, or a real display to watch.",
              file=sys.stderr)
    else:
        print("[mcp --window] watching window open — the agent's moves render live.", file=sys.stderr)

    try:
        build_server().run()                         # stdio server on the main thread
    finally:
        win = state.get("window")
        if win is not None:
            win.stop()
            t.join(timeout=2.0)


def main(argv: List[str] = None) -> None:
    """Stdio entrypoint. `--window` also opens a visible window mirroring the session."""
    import argparse
    ap = argparse.ArgumentParser(prog="mcp", description="Ultima IV MCP server (stdio).")
    ap.add_argument("--window", action="store_true",
                    help="also open a visible window so a human can watch the agent play live")
    ap.add_argument("--which", choices=("ega", "cga"), default="ega")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="window pacing: >1 slower, <1 faster (ticks held per applied move)")
    args = ap.parse_args(argv)

    if args.window:
        serve_windowed(which=args.which, action_every=max(1, round(6 * args.speed)))
    else:
        build_server().run()


if __name__ == "__main__":
    main()
