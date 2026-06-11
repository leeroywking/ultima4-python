"""PygameStage — the live "watch the agent play" front-end for the demo Director.

When a Director has a stage attached, each verb it runs (a step taken, a word said, a blow
struck) is shown on the real game screen and paced so a human can watch the character act —
the same renderer as interactive play (play.draw_game), driven by the scenario instead of the
keyboard. It can also capture the playthrough to an animated GIF, so the result is viewable
without a live display (and by the agent).

This is the only demo module that imports pygame; demo.py / demo_scenarios.py stay pure so the
headless transcript path has no window dependency. The Director talks to the stage through a
tiny duck-typed surface (`present`/`finish`), so it never imports pygame either.
"""
from __future__ import annotations

from typing import List, Optional


class StageQuit(Exception):
    """Raised inside present() when the viewer closes the window / presses Esc."""


class PygameStage:
    def __init__(self, which: str = "ega", speed: float = 1.0, realtime: bool = True,
                 capture: bool = False, capture_every: int = 2, downscale: int = 2):
        import pygame
        import play
        self.pygame = pygame
        self.play = play
        pygame.init()
        self.W = play.VIEW * play.SCALE
        self.H = play.VIEW * play.SCALE + play.PANEL_H
        self.screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("Ultima IV — live demo")
        self.A = play.Assets(which)
        self.clock = pygame.time.Clock()
        self.phase = 0
        self.speed = max(0.05, speed)              # >1 = slower (longer holds), <1 = faster
        self.realtime = realtime                   # True: pace to wall-clock (live window).
        self.hz = play.DOS_TIMER_HZ                # False: render as fast as possible (GIF/CI)
        self.frames: Optional[List] = [] if capture else None
        self._cap_every = max(1, capture_every)
        self._downscale = max(1, downscale)
        self._cap_i = 0

    def _pump(self) -> None:
        for ev in self.pygame.event.get():
            if ev.type == self.pygame.QUIT:
                raise StageQuit()
            if ev.type == self.pygame.KEYDOWN and ev.key == self.pygame.K_ESCAPE:
                raise StageQuit()

    def _capture(self) -> None:
        if self.frames is None:
            return
        self._cap_i += 1
        if self._cap_i % self._cap_every:
            return
        from PIL import Image
        buf = self.pygame.image.tostring(self.screen, "RGB")
        img = Image.frombytes("RGB", (self.W, self.H), buf)
        if self._downscale > 1:
            img = img.resize((self.W // self._downscale, self.H // self._downscale))
        self.frames.append(img)

    def present(self, game, banner: str = "", hold: float = 0.6, input_text: str = "") -> None:
        """Animate the current game state for `hold` seconds (scaled by speed), then return."""
        ticks = max(1, int(hold * self.speed * self.hz))
        if not self.realtime:
            ticks = min(ticks, 3)                  # GIF/CI: a few frames per beat, no sleeping
        for _ in range(ticks):
            self._pump()
            self.phase += 1
            game.tick_moons()
            self.play.draw_game(self.screen, self.A, game, self.phase // 4,
                                banner=banner or None, input_text=input_text)
            self._capture()
            if self.realtime:
                self.clock.tick(self.hz)

    def finish(self, game, banner: str = "", linger: float = 2.0) -> None:
        try:
            self.present(game, banner=banner, hold=linger)
        except StageQuit:
            pass

    def save_gif(self, path: str, fps: int = 10) -> Optional[str]:
        if not self.frames:
            return None
        self.frames[0].save(path, save_all=True, append_images=self.frames[1:],
                            duration=int(1000 / fps), loop=0, optimize=True)
        return path

    def save_shots(self, directory: str) -> int:
        if not self.frames:
            return 0
        from pathlib import Path
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(self.frames):
            img.save(d / f"frame_{i:04d}.png")
        return len(self.frames)

    def close(self) -> None:
        self.pygame.quit()
