"""Interaction layer implementing celebratory behaviors."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Callable, List, Optional

from .config import config
from .log import logger
from .motion import MotionController

try:  # pragma: no cover - hardware dependency
    from robot_hat import Music  # type: ignore
except Exception:  # pragma: no cover - hardware dependency
    Music = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CELEBRATION_SOUND = PROJECT_ROOT / "sounds" / "dog_sound.wav"
SPEAKER_ENABLE_CMD = "pinctrl set 20 op dh"


class InteractionManager:
    """Provides celebration behaviors triggered by the motion controller."""

    def __init__(self, motion: MotionController) -> None:
        self.motion = motion
        self.cfg = config.interaction
        self._sound_enabled = bool(self.cfg.enable_sound)
        self._music: Optional["Music"] = None
        self._sound_volume = max(0, min(100, int(self.cfg.sound_volume)))
        self._sound_path = self._resolve_sound_path()
        if self._sound_enabled:
            self._init_sound()
        self._celebrations: List[Callable[[], None]] = [
            self._celebration_spin,
            self._celebration_bounce,
        ]
        self.motion.register_celebration_handler(self.perform_celebration)
        logger.info("Interaction ready with %s celebration behaviors", len(self._celebrations))

    def tick(self, target_visible: bool) -> None:  # pragma: no cover - unused hook
        return

    # ------------------------------------------------------------------
    def perform_celebration(self) -> None:
        behavior = random.choice(self._celebrations)
        logger.info("Starting celebration: %s", behavior.__name__)
        self._play_sound()
        # behavior()

    def _celebration_spin(self) -> None:
        robot = self.motion.robot
        duration = self.motion.cfg.celebration_duration
        speed = max(self.motion.cfg.forward_speed, 40)
        try:
            robot.set_dir_servo_angle(60)
        except Exception:
            pass
        robot.forward(speed)
        time.sleep(duration)
        robot.stop()
        try:
            robot.set_dir_servo_angle(0)
            robot.set_cam_tilt_angle(0)
        except Exception:
            pass
        self.motion.reset_target_time()

    def _celebration_bounce(self) -> None:
        robot = self.motion.robot
        duration = 5.0
        speed = max(self.motion.cfg.forward_speed, 20)
        end_time = time.monotonic() + duration
        try:
            robot.set_dir_servo_angle(0)
        except Exception:
            pass
        while time.monotonic() < end_time:
            try:
                robot.set_cam_tilt_angle(15)
            except Exception:
                pass
            robot.forward(speed)
            time.sleep(0.6)
            try:
                robot.set_cam_tilt_angle(-10)
            except Exception:
                pass
            robot.backward(speed)
            time.sleep(0.6)
        robot.stop()
        try:
            robot.set_cam_tilt_angle(0)
        except Exception:
            pass
        self.motion.reset_target_time()

    # ------------------------------------------------------------------
    def _resolve_sound_path(self) -> Path:
        candidates = list(self.cfg.sound_files) or [DEFAULT_CELEBRATION_SOUND]
        for candidate in candidates:
            path = Path(candidate)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.exists():
                return path
        return DEFAULT_CELEBRATION_SOUND

    def _init_sound(self) -> None:
        if Music is None:
            logger.warning("robot_hat Music driver unavailable - disabling celebration sound")
            self._sound_enabled = False
            return
        try:
            os.popen(SPEAKER_ENABLE_CMD)
        except Exception as exc:  # pragma: no cover - optional
            logger.debug("Speaker enable command failed: %s", exc)
        try:
            self._music = Music()
        except Exception as exc:
            self._sound_enabled = False
            logger.warning("Failed to initialize celebration speaker: %s", exc)

    def _play_sound(self) -> None:
        if not self._sound_enabled or self._music is None:
            return
        if not self._sound_path.exists():
            logger.warning("Celebration sound missing: %s", self._sound_path)
            return
        try:
            play_threaded = getattr(self._music, "sound_play_threading", None)
            if callable(play_threaded):
                play_threaded(str(self._sound_path), self._sound_volume)
            else:
                self._music.sound_play(str(self._sound_path), self._sound_volume)
        except Exception as exc:
            logger.warning("Unable to play celebration sound: %s", exc)


__all__ = ["InteractionManager"]
