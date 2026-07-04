# Ultima IV — Python port you play *with your agent*

A faithful, agent-playable Python port of *Ultima IV: Quest of the Avatar* (1987, Origin Systems),
based on the community decompilation of the DOS executables (by ergonomy_joe). It's **self-contained
— clone and play, no original game files needed** — and it's built so an AI agent can play it while
you **watch each turn**.

## Quick start (play it with your agent in Claude Code)

Paste this to a fresh Claude Code agent:

> Clone https://github.com/leeroywking/ultima4-python, then set it up so I can watch you play.
> Run `./run test` to build and verify (expect 81/81), then `./run install-mcp` to register the
> game's MCP tools. Then tell me to **restart Claude Code and approve the `ultima4` server** — and
> once I've done that and said go, play Ultima IV using the `mcp__ultima4__*` tools (start by meeting
> Lord British) so every turn shows up here for me to watch. Don't play it headlessly.

What happens:

1. **Clone + build** — `git clone …` then `./run test` bootstraps a virtualenv (needs `python3`,
   internet for the first `pip install`) and runs the self-test suite (`81/81`).
2. **Register the MCP server** — `./run install-mcp` (one command; user scope, so it works from any
   folder). The repo also ships a project `.mcp.json` as an alternative.
3. **Restart Claude Code and approve** the `ultima4` server when prompted (this is a one-time
   security approval).
4. **Play** — ask the agent to play; each `observe`/`act` renders in the conversation, so you follow
   along move by move.

## Other ways to run it

- `./run` — **play it yourself** with the keyboard (opens the game window).
- `./run watch` — watch an **agent play live in the game window** (needs a display, not plain SSH).
- `./run mcp --window` — run the MCP server **with a visible window**, so a human watches an
  external/MCP-driven agent play live (headless `./run mcp` if you just want the tools).
- `./run demo` — scripted set-piece playthroughs (`./run demo` lists them).
- `./run smoke [out.png]` — headless one-frame render to a PNG (CI / display-less check).
- `./run agent-play --do "move N" --do "key T" …` — headless, stateless CLI (for scripting/testing).

## What's inside

The game reads only editable plain-text/PNG assets at runtime — graphics (`u4py/assets/*.png`),
maps (`data/maps/*.txt`), dialogue (`data/dialogue/*.json`), intro/menus (`data/intro/*.json`), the
party seed (`data/party_start.json`). Edit a JSON or PNG and the game changes live, no code change.
The engine lives in `u4py/`; see [`u4py/README.md`](u4py/README.md) for the code layout,
[`u4py/docs/AGENTS.md`](u4py/docs/AGENTS.md) for the agent observe/act contract, and
[`u4py/ROADMAP.md`](u4py/ROADMAP.md) for the plan.

## About the game content

This is a free, non-commercial fan port. *Ultima IV* was created by Lord British (Richard Garriott)
and Origin Systems, which Origin/EA released as freeware. All Ultima trademarks and copyrights
remain with their owners; this project has no affiliation with or endorsement by them. See
[`u4py/docs/AGENTS.md`](u4py/docs/AGENTS.md).
