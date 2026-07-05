"""LiveWindow — a free-running, human-watchable window for an AGENT-driven Ultima IV session.

The demo/stage path is *synchronous*: the Director applies an action, then renders that beat,
then the next. That is great for a scripted playthrough but wrong for "an agent plays while a
human watches": there the window must keep animating (creatures shuffling, moons turning) at the
DOS animation rate while actions arrive *whenever the agent decides them*.

So this module decouples the two:

- The **render loop runs on the MAIN thread** (pygame requires it). Each tick it pumps events,
  maybe drains ONE action from a thread-safe queue and applies it to the `Game`, advances the
  animation phase, and draws one frame via the shared `play.draw_game`. It ticks at
  `play.DOS_TIMER_HZ` (18 Hz, int 0x1C — see play.py / LOW.ASM), the same clock interactive play
  uses; nothing here invents a 60 fps.
- An **agent runs on a BACKGROUND thread**. It only ever READS observations (`env.observe()`) and
  PUSHES action strings onto the queue. It never touches pygame and never touches the Game state
  directly, because `Game` is not thread-safe — every mutation happens in the render loop.

Pacing: actions are applied at most one per `action_every` ticks (~0.5 s by default) so a human
can actually SEE each move land, rather than the whole queue flushing in one frame.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Union

# play.py + env.py live next to / above this package; importing here keeps callers simple.
import play
from .env import UltimaEnv
from .game import Game

# A policy maps the current observation (a plain dict from env.observe()) to an action string.
Policy = Callable[[dict], Optional[str]]


@dataclass
class _Job:
    """Work submitted from another thread to run ON the render thread (so it can safely mutate the
    non-thread-safe Game), with its result/exception handed back via an Event. Either a one-shot
    callable `fn`, or a `gen` generator that yields once per internal turn — the render loop advances
    it one step per pacing window, so a multi-turn op (travel/wait/play) ANIMATES instead of jumping.
    A generator signals completion by `return`ing the final result (StopIteration.value)."""
    fn: Optional[Callable[[], Any]]
    done: threading.Event
    label: Optional[str] = None
    box: dict = field(default_factory=dict)
    gen: Optional[Any] = None


class LiveWindow:
    """A continuously-rendering window that applies asynchronously-queued agent actions.

    Construct with an `UltimaEnv` (preferred — actions go through `env.act`) or a bare `Game`
    (we wrap it in an env). Call `run()` on the main thread; from any other thread call
    `enqueue("move N")`, or use `play_actions(...)` / `run_with_agent(...)` which spawn the
    background feeder for you.
    """

    def __init__(self, env_or_game: Union[UltimaEnv, Game], which: str = "ega",
                 fps: int = play.DOS_TIMER_HZ, action_every: int = 8):
        # Accept either the agent-facing env or a raw Game.
        if isinstance(env_or_game, UltimaEnv):
            self.env = env_or_game
        else:
            self.env = UltimaEnv(game=env_or_game)
        # The render loop drives the real-time moon clock (catch_up_moons per frame), so the env's
        # observe/act must NOT also advance it (that would double-count and race the render thread).
        self.env.drive_clock = False

        self.which = which
        self.fps = max(1, int(fps))
        # ~0.5 s between applied actions at 18 Hz; configurable so the human can keep up.
        self.action_every = max(1, int(action_every))

        self.queue: "queue.Queue[str]" = queue.Queue()
        self._active_op: Optional[_Job] = None  # a generator job being animated one step per slot
        self._stop = threading.Event()
        self._agent_done = threading.Event()   # set by a finished background feeder

        # Banner state (what the viewer reads): the last applied action + last game message.
        self._last_action: Optional[str] = None
        self._last_message: Optional[str] = None
        self.applied = 0                        # count of actions actually applied (test hook)

        # pygame setup MUST happen on the thread that will run() — but Assets needs a display
        # mode set first, and with SDL_VIDEODRIVER=dummy this is safe headlessly too.
        play.pygame.init()
        self.W = play.VIEW * play.SCALE
        self.H = play.VIEW * play.SCALE + play.PANEL_H
        self.screen = play.pygame.display.set_mode((self.W, self.H))
        play.pygame.display.set_caption("Ultima IV — watch the agent")
        self.assets = play.Assets(which)
        self.clock = play.pygame.time.Clock()
        self.phase = 0

    @property
    def game(self) -> Game:
        """Always the env's CURRENT game — so `env.reset()` (a new_game) is reflected live."""
        return self.env.game

    # --- thread-safe action intake ------------------------------------------
    def enqueue(self, action: str) -> None:
        """Push an action string onto the queue. Safe to call from any thread."""
        if action:
            self.queue.put(action)

    def submit(self, fn: Callable[[], Any], label: Optional[str] = None,
               timeout: float = 15.0) -> Any:
        """Run `fn` ON the render thread and return its result. Safe from any thread.

        Use this to mutate the Game from an external controller (e.g. the MCP server): the render
        loop applies it between frames, so the human sees each change land and there's no data race
        with drawing. `label` (e.g. the action string) shows in the on-screen banner. If the window
        is already stopped, `fn` runs inline on the caller's thread as a best-effort fallback."""
        if self._stop.is_set():
            return fn()
        job = _Job(fn, threading.Event(), label)
        self.queue.put(job)
        if not job.done.wait(timeout):
            raise TimeoutError("LiveWindow.submit: render thread did not apply in time")
        if "err" in job.box:
            raise job.box["err"]
        return job.box.get("val")

    def submit_op(self, gen: Any, label: Optional[str] = None, timeout: float = 300.0) -> Any:
        """Run a stepped operation (a generator that yields once per internal turn) ON the render
        thread, ANIMATED — one step per pacing window, so the human watches every turn. Returns the
        generator's `return` value. Safe from any thread. If the window is stopped, the op is driven
        to completion inline as a fallback."""
        if self._stop.is_set():
            try:
                while True:
                    next(gen)
            except StopIteration as e:
                return e.value
        job = _Job(None, threading.Event(), label, gen=gen)
        self.queue.put(job)
        if not job.done.wait(timeout):
            raise TimeoutError("LiveWindow.submit_op: op did not finish in time")
        if "err" in job.box:
            raise job.box["err"]
        return job.box.get("val")

    def stop(self) -> None:
        """Ask the render loop to exit cleanly (safe from any thread)."""
        self._stop.set()

    # --- the main-thread render loop ----------------------------------------
    def run(self, max_ticks: Optional[int] = None,
            stop_when_idle: bool = False) -> int:
        """Render continuously until QUIT/Esc, `stop()`, the agent finishes, or `max_ticks`.

        `max_ticks` bounds the loop (used by the headless self-check so tests never hang).
        `stop_when_idle` exits once the agent thread is done AND the queue has drained — handy
        for replaying a finite action list and then leaving the final frame up briefly.
        Returns the number of actions applied (lets tests assert progress).
        """
        pg = play.pygame
        tick = 0
        idle_grace = 0
        while not self._stop.is_set():
            # 1) input: QUIT or Esc ends the session immediately.
            for ev in pg.event.get():
                if ev.type == pg.QUIT:
                    self._stop.set()
                elif ev.type == pg.KEYDOWN and ev.key == pg.K_ESCAPE:
                    self._stop.set()
            if self._stop.is_set():
                break

            # 2) pacing: every `action_every` ticks, advance ONE turn — a step of the active
            #    generator op (travel/wait/play, so it animates) or one queued action. Render
            #    thread only (Game is not thread-safe — all mutation lives here).
            if tick % self.action_every == 0:
                if self._active_op is not None:
                    self._step_active_op()
                else:
                    self._apply_one()

            # 3) animate: moons + creature shuffle run on the wall clock, not on movement.
            self.phase += 1
            self.game.catch_up_moons()

            # 4) draw one frame with a caption the viewer can follow.
            play.draw_game(self.screen, self.assets, self.game, self.phase // 4,
                           banner=self._banner())

            # 5) exit conditions for finite sessions.
            if self.game.won:
                # let the victory frame linger a moment, then stop.
                self._hold(self._banner(), seconds=2.0)
                break
            if stop_when_idle and self._agent_done.is_set() and self.queue.empty():
                idle_grace += 1
                if idle_grace > self.fps * 2:        # ~2 s after the last action, leave.
                    break
            tick += 1
            if max_ticks is not None and tick >= max_ticks:
                break
            self.clock.tick(self.fps)
        return self.applied

    def _apply_one(self) -> bool:
        """Drain and apply a single queued item — an action string, or a submitted `_Job`
        (an external controller's callable). Render thread only (Game is not thread-safe)."""
        try:
            item = self.queue.get_nowait()
        except queue.Empty:
            return False
        if isinstance(item, _Job) and item.gen is not None:
            self._active_op = item                      # animate it, one step per pacing window
            if item.label:
                self._last_action = item.label
            return True
        if isinstance(item, _Job):
            try:
                item.box["val"] = item.fn()
            except Exception as e:                      # hand the failure back to submit()
                item.box["err"] = e
            finally:
                item.done.set()
            if item.label:
                self._last_action = item.label
        else:
            self.env.act(item)
            self._last_action = item
        self.applied += 1
        msgs = [m for m in self.game.messages if m]
        self._last_message = msgs[-1] if msgs else self._last_message
        return True

    def _step_active_op(self) -> None:
        """Advance the active generator op by one turn (render thread only). On completion, hand the
        op's return value back to the waiting submit_op()."""
        job = self._active_op
        try:
            next(job.gen)                               # run one internal turn, up to its next yield
            self.applied += 1
        except StopIteration as e:
            job.box["val"] = e.value
            job.done.set()
            self._active_op = None
        except Exception as e:
            job.box["err"] = e
            job.done.set()
            self._active_op = None
        msgs = [m for m in self.game.messages if m]
        self._last_message = msgs[-1] if msgs else self._last_message

    def _banner(self) -> Optional[str]:
        parts = []
        if self._last_action:
            parts.append(f"> {self._last_action}")
        if self._last_message:
            parts.append(self._last_message)
        return "  ".join(parts) if parts else None

    def _hold(self, banner: Optional[str], seconds: float) -> None:
        """Keep animating the current state for a few seconds (e.g. on a win)."""
        for _ in range(int(seconds * self.fps)):
            for ev in play.pygame.event.get():
                if ev.type == play.pygame.QUIT:
                    return
            self.phase += 1
            self.game.catch_up_moons()
            play.draw_game(self.screen, self.assets, self.game, self.phase // 4, banner=banner)
            self.clock.tick(self.fps)

    def close(self) -> None:
        play.pygame.quit()

    # --- background drivers ---------------------------------------------------
    def play_actions(self, actions: List[str], delay: float = 0.0,
                     max_ticks: Optional[int] = None) -> int:
        """Replay a fixed action list LIVE: spawn a feeder thread, then run the window.

        The feeder simply enqueues each action (optionally sleeping `delay` s between pushes);
        the render loop's own pacing (`action_every`) controls how fast they actually land.
        Returns actions applied.
        """
        def feeder():
            for a in actions:
                if self._stop.is_set():
                    break
                self.enqueue(a)
                if delay:
                    time.sleep(delay)
            self._agent_done.set()

        t = threading.Thread(target=feeder, daemon=True)
        t.start()
        try:
            return self.run(max_ticks=max_ticks, stop_when_idle=True)
        finally:
            self._stop.set()
            t.join(timeout=1.0)

    def run_with_agent(self, policy: Policy, max_turns: int = 200,
                       max_ticks: Optional[int] = None, think_delay: float = 0.05) -> int:
        """Run the window while a `policy(observation) -> action_str` chooses moves.

        The policy runs on a BACKGROUND thread: it reads `env.observe()` (accepting minor
        staleness — the real apply happens in the render loop), enqueues the chosen action, and
        repeats under a `max_turns` budget. It stops on `won`, on budget, or when the window
        closes. To avoid sprinting ahead of what the human sees, the feeder waits for the queue
        to drain before deciding the next move.
        """
        def feeder():
            turns = 0
            while turns < max_turns and not self._stop.is_set() and not self.game.won:
                # don't get more than a move or two ahead of the render loop.
                if self.queue.qsize() >= 2:
                    time.sleep(think_delay)
                    continue
                try:
                    obs = self.env.observe()
                except Exception:
                    break
                if obs.get("won"):
                    break
                try:
                    action = policy(obs)
                except Exception:
                    action = None
                if not action:
                    break
                self.enqueue(action)
                turns += 1
                time.sleep(think_delay)
            self._agent_done.set()

        t = threading.Thread(target=feeder, daemon=True)
        t.start()
        try:
            return self.run(max_ticks=max_ticks, stop_when_idle=True)
        finally:
            self._stop.set()
            t.join(timeout=1.0)


# --- a tiny built-in policy so `watch` always has something to show ----------
def wander_policy(seed: int = 0) -> Policy:
    """A simple, robust policy: pick a legal move, occasionally Enter/Talk, mostly wander.

    It reads only the observation's `legal_actions` so it never issues an illegal key. This is
    deliberately dumb — its only job is to produce a watchable stream of real moves.
    """
    import random
    rng = random.Random(seed)
    moves = ["move N", "move S", "move E", "move W"]

    def policy(obs: dict) -> Optional[str]:
        legal = obs.get("legal_actions") or []
        # If a conversation is open, politely leave it so we keep wandering.
        if obs.get("interaction", {}).get("active"):
            return "say bye"
        # If standing on a town/castle-ish entry, try to Enter sometimes.
        if "key E" in legal and rng.random() < 0.15:
            return "key E"
        choices = [m for m in moves if m in legal] or ["pass"]
        return rng.choice(choices)

    return policy
