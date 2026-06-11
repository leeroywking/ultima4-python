"""Knowledge base for the tutor agent.

Static U4 domain knowledge the tutor reasons over: the quest dependency graph, per-virtue
requirements (rune, mantra, shrine location, what raises/lowers karma), item locations, and
walkthrough milestones. Sourced from the cluebook/manual (staged in ~/Downloads) plus the
decompiled tables. Separate from live game state — this is what's *true about U4*, which the
tutor combines with what's *true right now* (agent.rpc) to give grounded, non-spoilery hints.
"""
