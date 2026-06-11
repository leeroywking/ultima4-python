# Ultima IV → Python rewrite — working rules

This repo is a **faithful port** of Ultima IV from the decompiled DOS source. The Python game
is in `u4py/`; the original is in `u4/` (`SRC/*.C`, `*.H`, `*.ASM`), with a portable-C
reference in `forVS/`. Game data files are in `u4py/data/`.

## Rule #1 — reference the original FIRST (non-negotiable)

When (re)building any behavior from the original game, **derive it from the original source,
not from modern convention, a round number, or memory (yours or the user's).**

Before writing code for a ported feature:
1. Locate it in `u4/SRC/*.C` / `*.H` / `*.ASM` (or `forVS/`, or the data files) and **cite the
   function/constant in a comment** (e.g. `# C: U4_ANIM.C C_3A80`).
2. Take positions, sizes, **timings/rates**, colors, tables, formulas, and text **from the
   source**. A modern/round value (e.g. `60` fps, "top-right corner") is a smell that you're
   guessing — go find the real value.
3. If the source genuinely doesn't pin a value down, **say so** and state the smallest
   defensible inference; don't silently invent.
4. Deviate only deliberately, and record the deviation as a known simplification in
   `u4py/ROADMAP.md`.

Examples of getting this wrong (don't repeat): the animation tick is the DOS **int 0x1C timer
= 18.2 Hz** (`LOW.ASM`), not 60 fps; the moon-phase HUD is **top-center, text col 11–12 row 0**
(`U4_ANIM.C C_3A80`), drawn as charset glyphs `0x14+((phase-1)&7)`, not a hand-picked corner.

## Other standing rules
- Faithful port first (verify against original), then refactor toward legible, data-driven code.
- Every feature ships with a headless check in `tools/selftest.py`; keep `./run test` green.
- `u4py/ROADMAP.md` is the live plan; the project memory holds context across sessions.

## Playing the game as an agent (if the human asks you to play / demo it)

This game is built to be **played by you**. If the user asks you to play, demo, or explore the
game, do it — here's how, in order of preference:

1. **MCP tools (preferred).** This repo ships a `.mcp.json`, so opening it in Claude Code makes an
   `ultima4` MCP server available (approve it if prompted; tools are named `mcp__ultima4__*`). Play
   the loop: `new_game(seed)` → `observe()` → choose from the returned `legal_actions` → `act(...)`
   → repeat. Read the observation's `view_ascii`, `visible`, `standing_on`, and `messages` to
   decide. If the tools aren't present yet (not approved / not restarted), use option 2 — don't
   block.
2. **CLI (zero-setup, always works).** `./run agent-play --do "move N" --do "key T" ...` rebuilds
   from the seed and replays the whole action list each call (it's stateless and deterministic),
   printing the observation + `legal_actions`. Append one `--do` per turn to play on. Or run the
   reference policy: `./run agent-demo`.
3. **Let the human watch:** `./run watch` plays live in the game window (the character moves/talks/
   fights on screen); `./run demo` lists scripted set-piece playthroughs.

**Action grammar** (same everywhere): `"move N|S|E|W"`, `"key <LETTER>"` (T=Talk, E=Enter, C=Cast,
Z=Ztats, K=Klimb, D=Descend, X=eXit…), `"say <text>"` (into an active Talk/shop), `"pass"`. The
full observe/act contract is in `u4py/docs/AGENTS.md`. Goal of a playthrough is up to the human;
the win condition is the Abyss/Codex (`observation["won"]`). To wire the MCP server on a fresh
machine: `./run install-mcp` (one command, user scope).
