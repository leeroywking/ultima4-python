"""The runtime agent layer — the reason this port exists.

Two agents sit on top of the live game:
  - editor.py  — WRITE: turns natural language into game-state mutations.
  - tutor.py   — READ:  answers the player's questions from live state + a knowledge base.

Both go through rpc.py, a clean, serializable state-query/mutate interface over the engine,
so neither agent reaches into engine internals directly. See knowledge/ for the tutor's
quest/virtue data. All v1 stubs.
"""
