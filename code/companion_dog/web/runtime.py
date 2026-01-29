"""Runtime helpers powering the pet follower web API."""
from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple
import tempfile

import cv2

from utils.interaction import InteractionManager
from utils.log import logger
from utils.motion import MotionController
from utils.vision import CameraStream, DetectionResult, DogDetector
from utils.cloud_client import send_frame_bgr, send_video_file

LOOP_DELAY = 0.02
SMART_SNAPSHOT_STILLNESS_SEC = 10.0
SMART_SNAPSHOT_TOLERANCE_PX = 30.0
SMART_SNAPSHOT_COOLDOWN_SEC = 300.0
SUDDEN_MOVE_DISTANCE_PX = 60.0
SUDDEN_MOVE_COOLDOWN_SEC = 60.0


class EventBus:
    """Fan out runtime events (status/log) to async listeners."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listeners: List[asyncio.Queue] = []
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._listeners.append(queue)
        return queue

    def unregister(self, queue: asyncio.Queue) -> None:
        with self._lock:
            if queue in self._listeners:
                self._listeners.remove(queue)

    def emit(self, payload: Dict[str, Any]) -> None:
        loop = self._loop
        if loop is None:
            return
        with self._lock:
            queues = list(self._listeners)
        for queue in queues:
            try:
                asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
            except RuntimeError:
                # Loop might be closed during shutdown.
                pass


class CameraManager:
    """Background thread that keeps a single camera instance warm."""

    def __init__(self) -> None:
        self._camera = CameraStream()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Condition(self._frame_lock)
        self._latest_frame: Optional[Any] = None  # OpenCV ndarray

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        logger.info("Camera manager starting up")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        self._camera.start()
        try:
            while not self._stop.is_set():
                frame = self._camera.read()
                if frame is None:
                    time.sleep(0.05)
                    continue
                with self._frame_ready:
                    self._latest_frame = frame
                    self._frame_ready.notify_all()
        finally:
            self._camera.stop()
            with self._frame_ready:
                self._latest_frame = None
                self._frame_ready.notify_all()

    def get_frame(self, *, wait: bool = True, timeout: float = 1.0, copy_frame: bool = True):
        """Return the latest frame, waiting if requested."""
        with self._frame_ready:
            if wait and self._latest_frame is None:
                self._frame_ready.wait(timeout)
            frame = self._latest_frame
        if frame is None:
            return None
        return frame.copy() if copy_frame else frame

    def mjpeg_generator(self) -> Iterable[bytes]:
        boundary = b"--frame"
        while True:
            frame = self.get_frame(wait=True, timeout=1.0, copy_frame=True)
            if frame is None:
                continue
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            payload = buf.tobytes()
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"


@dataclass
class RuntimeState:
    mode: str = "idle"
    message: str = "Idle"
    target_visible: bool = False
    detection: Dict[str, Any] = field(default_factory=dict)
    safety: Dict[str, Any] = field(default_factory=dict)
    motion: Dict[str, Any] = field(default_factory=dict)
    fps: float = 0.0
    last_log: str = ""
    auto_recording: Dict[str, Any] = field(default_factory=dict)
    smart_snapshot: Dict[str, Any] = field(default_factory=dict)
    movement_recording: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "message": self.message,
            "target_visible": self.target_visible,
            "detection": self.detection,
            "safety": self.safety,
            "motion": self.motion,
            "fps": self.fps,
            "last_log": self.last_log,
            "auto_recording": self.auto_recording,
            "smart_snapshot": self.smart_snapshot,
            "movement_recording": self.movement_recording,
        }


class PetFollowerRuntime:
    """Orchestrates the pet follower behavior for the web API."""

    def __init__(self, camera: CameraManager, events: EventBus) -> None:
        self._camera = camera
        self._events = events
        self._motion = MotionController()
        self._interaction = InteractionManager(self._motion)
        self._detector = DogDetector()
        self._state = RuntimeState()
        self._state_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._fps_samples: Deque[float] = deque(maxlen=60)
        self._last_detection: Optional[DetectionResult] = None
        self._last_detection_time = 0.0
        self._target_visible = False
        self._force_search = threading.Event()
        self._recording_lock = threading.Lock()
        self._auto_record_thread: Optional[threading.Thread] = None
        self._auto_record_enabled = False
        self._auto_record_interval = 180.0
        self._auto_record_duration = 2.0 # control the length of recording
        self._last_auto_record = 0.0
        self._last_auto_record_wall = 0.0
        self._stillness_last_center: Optional[Tuple[float, float]] = None
        self._stillness_last_motion = 0.0
        self._stillness_last_center_time = 0.0
        self._smart_snapshot_last_capture = 0.0
        self._smart_snapshot_last_wall = 0.0
        self._movement_record_last_trigger = 0.0
        self._movement_record_last_wall = 0.0
        self._movement_record_active = False
        self._last_log_message: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        with self._state_lock:
            return json.loads(json.dumps(self._state.to_dict()))

    def start_following(self) -> str:
        if self._detector.model is None:
            raise RuntimeError("YOLO model not loaded; cannot start follow mode")
        if self._thread and self._thread.is_alive():
            return "Follow mode already running"
        self._stop_event.clear()
        self._camera.start()
        self._thread = threading.Thread(target=self._loop, name="pet-follower", daemon=True)
        self._thread.start()
        self._update_state(mode="auto", message="Entering follow mode")
        return "Pet follower started"

    def stop_following(self) -> str:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2.0)
        self._thread = None
        self._motion.stop()
        self._update_state(mode="idle", message="Stopped", target_visible=False)
        return "Pet follower stopped"

    def reset(self) -> str:
        self._motion.stop()
        self._motion.reset_target_time()
        self._force_search.clear()
        self._update_state(message="State reset", target_visible=False)
        return "State reset"

    def celebrate(self) -> str:
        self._interaction.perform_celebration()
        self._update_state(message="Celebration requested")
        return "Celebration triggered"

    def force_search(self) -> str:
        self._force_search.set()
        self._update_state(message="Search command queued")
        return "Search triggered"

    def capture_snapshot(self) -> str:
        frame = self._camera.get_frame(wait=True, timeout=1.0, copy_frame=True)
        if frame is None:
            raise RuntimeError("Unable to capture frame right now")
        send_frame_bgr(frame)
        self._update_state(message="Snapshot uploaded to cloud")
        return "Snapshot sent"

    def record_video(self, duration: float = 10.0, fps: int = 15) -> str:
        duration = max(1.0, min(float(duration), 60.0))
        fps = max(5, min(int(fps), 30))
        if not self._recording_lock.acquire(blocking=False):
            raise RuntimeError("Video recording already running")
        try:
            self._update_state(auto_recording=self._auto_record_state())
            return self._capture_and_upload_video(duration, fps, auto=False)
        finally:
            self._recording_lock.release()
            self._update_state(auto_recording=self._auto_record_state())

    def manual_drive(self, direction: str, speed: int, duration: float) -> str:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Follower is active; stop it before manual drive")
        robot = self._motion.robot
        speed = max(0, min(100, int(speed)))
        duration = max(0.1, min(3.0, float(duration)))
        direction = (direction or "").lower()
        logger.info("Manual drive direction=%s speed=%s duration=%s", direction, speed, duration)
        if direction == "forward":
            robot.forward(speed)
        elif direction == "backward":
            robot.backward(speed)
        elif direction == "left":
            robot.set_dir_servo_angle(-30)
            robot.forward(speed)
        elif direction == "right":
            robot.set_dir_servo_angle(30)
            robot.forward(speed)
        elif direction == "stop":
            robot.stop()
            robot.set_dir_servo_angle(0)
            return "Stopped"
        else:
            raise RuntimeError("Unknown direction; allowed forward/backward/left/right/stop")
        time.sleep(duration)
        robot.stop()
        robot.set_dir_servo_angle(0)
        self._update_state(message=f"Manual drive {direction}")
        return "Manual drive complete"

    def mark_event(self, note: str | None) -> str:
        msg = note or "Untitled event"
        logger.info("Mark event: %s", msg)
        self._update_state(message=f"Event: {msg}")
        return "Event recorded"

    def configure_auto_recording(
        self, *, enabled: Optional[bool] = None, interval: Optional[float] = None
    ) -> str:
        if enabled is not None:
            self._auto_record_enabled = bool(enabled)
            self._last_auto_record = 0.0
        if interval is not None:
            interval = max(30.0, min(float(interval), 900.0))
            self._auto_record_interval = interval
        self._update_state(
            message="Auto recording updated",
            auto_recording=self._auto_record_state(),
        )
        return "Auto recording settings updated"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        logger.info("Pet follower loop starting")
        self._motion.reset_target_time()
        last_loop = time.monotonic()
        try:
            while not self._stop_event.is_set():
                frame = self._camera.get_frame(wait=True, timeout=1.0, copy_frame=False)
                if frame is None:
                    continue
                now = time.monotonic()
                elapsed = now - last_loop
                last_loop = now
                if elapsed > 0:
                    self._fps_samples.append(1.0 / elapsed)

                detection = self._detector.detect_dog(frame)
                self._handle_smart_snapshot(frame, detection)
                active_detection, holding_last = self._resolve_detection(detection)
                target_visible = detection is not None
                safe_to_move = self._motion.update_safety()

                if self._force_search.is_set():
                    self._force_search.clear()
                    self._motion.reset_target_time()
                    self._motion.turn90(1)
                    self._log("Executing forced search")

                if not safe_to_move:
                    self._log(
                        "Movement blocked by safety check",
                        level="warning",
                        emit_event=False,
                    )
                else:
                    if active_detection is not None:
                        self._motion.track_target(active_detection)
                        if target_visible:
                            self._log("Target acquired; following")
                        elif holding_last:
                            self._log("Holding last heading, continuing search")
                    else:
                        self._log("No detection - Searching", verbose=True)
                        if not self._motion.search():
                            self._motion.turn90(1)
                            self._motion.reset_target_time()

                self._handle_auto_recording(target_visible)
                self._publish_state(active_detection, target_visible, safe_to_move)
                time.sleep(LOOP_DELAY)
        except Exception as exc:  # pragma: no cover - safety
            logger.exception("Follower loop crashed: %s", exc)
            self._update_state(message=f"Loop error: {exc}")
        finally:
            self._motion.stop()
            self._update_state(mode="idle", message="Automatic mode exited", target_visible=False)
            logger.info("Pet follower loop stopped")

    def _resolve_detection(self, detection: Optional[DetectionResult]):
        active = detection
        holding = False
        now = time.monotonic()
        if detection is not None:
            self._last_detection = detection
            self._last_detection_time = now
            self._target_visible = True
        elif self._last_detection is not None:
            age = now - self._last_detection_time
            if age <= self._motion.cfg.pursuit_hold_time:
                active = self._last_detection
                holding = True
            else:
                self._last_detection = None
                self._last_detection_time = 0.0
                self._target_visible = False
        return active, holding

    def _publish_state(self, detection: Optional[DetectionResult], target_visible: bool, safe: bool) -> None:
        detection_payload = self._serialize_detection(detection)
        safety = {
            "distance_cm": self._motion.safety.distance_cm,
            "cliff_detected": self._motion.safety.cliff_detected,
        }
        motion = {"safe_to_move": safe}
        fps = sum(self._fps_samples) / len(self._fps_samples) if self._fps_samples else 0.0
        self._update_state(
            detection=detection_payload or {},
            safety=safety,
            motion=motion,
            target_visible=target_visible,
            fps=round(fps, 2),
            auto_recording=self._auto_record_state(),
            smart_snapshot=self._smart_snapshot_state(),
            movement_recording=self._movement_record_state(),
        )

    def _serialize_detection(self, detection: Optional[DetectionResult]) -> Optional[Dict[str, Any]]:
        if detection is None:
            return None
        return {
            "center": [detection.center[0], detection.center[1]],
            "bbox": [float(v) for v in detection.bbox],
            "confidence": float(detection.confidence),
            "approx_distance_cm": detection.approx_distance_cm,
            "updated_at": time.time(),
        }

    def _log(
        self,
        message: str,
        *,
        level: str = "info",
        verbose: bool = False,
        emit_event: bool = True,
    ) -> None:
        duplicate = level == "info" and message == self._last_log_message
        if duplicate:
            return
        self._last_log_message = message
        if verbose:
            logger.debug(message)
        else:
            getattr(logger, level, logger.info)(message)
        self._update_state(message=message, last_log=message)
        if emit_event:
            self._events.emit({"type": "log", "level": level, "message": message})

    def _auto_record_state(self) -> Dict[str, Any]:
        now = time.monotonic()
        elapsed = now - self._last_auto_record if self._last_auto_record > 0 else float("inf")
        remaining = max(0.0, self._auto_record_interval - elapsed) if elapsed != float("inf") else 0.0
        eligible = elapsed >= self._auto_record_interval or self._last_auto_record == 0.0
        last_wall = self._last_auto_record_wall or None
        since_last = (
            (time.time() - self._last_auto_record_wall) if self._last_auto_record_wall else None
        )
        return {
            "enabled": self._auto_record_enabled,
            "interval": self._auto_record_interval,
            "seconds_until_next": 0.0 if eligible else remaining,
            "eligible": eligible,
            "active": self._recording_lock.locked(),
            "last_uploaded_at": last_wall,
            "seconds_since_last": since_last,
        }

    def _smart_snapshot_state(self) -> Dict[str, Any]:
        now = time.monotonic()
        if self._smart_snapshot_last_capture == 0.0:
            elapsed = float("inf")
        else:
            elapsed = now - self._smart_snapshot_last_capture
        eligible = elapsed == float("inf") or elapsed >= SMART_SNAPSHOT_COOLDOWN_SEC
        seconds_until = 0.0 if eligible else max(0.0, SMART_SNAPSHOT_COOLDOWN_SEC - elapsed)
        since_last = (
            (time.time() - self._smart_snapshot_last_wall)
            if self._smart_snapshot_last_wall
            else None
        )
        return {
            "eligible": eligible,
            "seconds_until_next": seconds_until,
            "cooldown_seconds": SMART_SNAPSHOT_COOLDOWN_SEC,
            "last_uploaded_at": self._smart_snapshot_last_wall or None,
            "stillness_required": SMART_SNAPSHOT_STILLNESS_SEC,
            "tolerance_px": SMART_SNAPSHOT_TOLERANCE_PX,
        }

    def _movement_record_state(self) -> Dict[str, Any]:
        now = time.monotonic()
        if self._movement_record_last_trigger == 0.0:
            elapsed = float("inf")
        else:
            elapsed = now - self._movement_record_last_trigger
        eligible = elapsed == float("inf") or elapsed >= SUDDEN_MOVE_COOLDOWN_SEC
        seconds_until = 0.0 if eligible else max(0.0, SUDDEN_MOVE_COOLDOWN_SEC - elapsed)
        since_last = (
            (time.time() - self._movement_record_last_wall)
            if self._movement_record_last_wall
            else None
        )
        return {
            "cooldown": SUDDEN_MOVE_COOLDOWN_SEC,
            "eligible": eligible,
            "seconds_until_next": seconds_until,
            "last_triggered_at": self._movement_record_last_wall or None,
            "seconds_since_last": since_last,
            "active": self._movement_record_active,
        }

    def _handle_auto_recording(self, target_visible: bool) -> None:
        if not self._auto_record_enabled or not target_visible:
            return
        if self._recording_lock.locked():
            return
        now = time.monotonic()
        last = self._last_auto_record if self._last_auto_record > 0 else 0.0
        elapsed = now - last if last > 0 else float("inf")
        if elapsed >= self._auto_record_interval:
            self._start_background_recording()
            self._update_state(auto_recording=self._auto_record_state())

    def _handle_smart_snapshot(self, frame, detection: Optional[DetectionResult]) -> None:
        now = time.monotonic()
        if detection is None:
            self._stillness_last_center = None
            self._stillness_last_motion = 0.0
            self._stillness_last_center_time = 0.0
            return
        center = detection.center
        if not center:
            return
        if self._stillness_last_center is None:
            self._stillness_last_center = center
            self._stillness_last_motion = now
            self._stillness_last_center_time = now
            return
        last_center_time = self._stillness_last_center_time or now
        prev_center = self._stillness_last_center
        movement_dx = center[0] - prev_center[0]
        movement_dy = center[1] - prev_center[1]
        movement = math.hypot(movement_dx, movement_dy)
        self._stillness_last_center = center
        self._stillness_last_center_time = now
        still_for = now - self._stillness_last_motion if self._stillness_last_motion else 0.0
        logger.info(
            "Smart snapshot movement=%.2f (dx=%.1f, dy=%.1f) still=%.2f target=(%.1f, %.1f)",
            movement,
            movement_dx,
            movement_dy,
            still_for,
            center[0],
            center[1],
        )
        elapsed_since_center = max(1e-6, now - last_center_time)
        speed_px = movement / elapsed_since_center
        movement_ready = (
            self._movement_record_last_trigger == 0.0
            or (now - self._movement_record_last_trigger) >= SUDDEN_MOVE_COOLDOWN_SEC
        )
        if (
            still_for >= SMART_SNAPSHOT_STILLNESS_SEC
            and movement >= SUDDEN_MOVE_DISTANCE_PX
            and movement_ready
        ):
            self._trigger_movement_recording(still_for, movement, speed_px)
        if movement > SMART_SNAPSHOT_TOLERANCE_PX:
            self._stillness_last_motion = now
            return
        if self._stillness_last_motion == 0.0:
            self._stillness_last_motion = now
            return
        if still_for < SMART_SNAPSHOT_STILLNESS_SEC:
            return
        last_capture = self._smart_snapshot_last_capture
        if last_capture and (now - last_capture) < SMART_SNAPSHOT_COOLDOWN_SEC:
            return
        frame_copy = frame.copy()
        try:
            send_frame_bgr(frame_copy)
        except Exception as exc:
            logger.warning("Smart snapshot failed: %s", exc)
            self._update_state(message=f"Smart snapshot failed: {exc}")
        else:
            self._smart_snapshot_last_capture = now
            self._smart_snapshot_last_wall = time.time()
            self._log("Smart snapshot uploaded - pet resting")
            self._update_state(smart_snapshot=self._smart_snapshot_state())
        finally:
            self._stillness_last_motion = now

    def _trigger_movement_recording(self, still_for: float, movement: float, speed_px: float) -> None:
        if self._recording_lock.locked() or self._movement_record_active:
            return

        def worker() -> None:
            if not self._recording_lock.acquire(blocking=False):
                self._movement_record_active = False
                return
            self._movement_record_active = True
            self._movement_record_last_trigger = time.monotonic()
            self._movement_record_last_wall = time.time()
            self._update_state(movement_recording=self._movement_record_state())
            start_msg = (
                f"Motion-triggered recording (Δ {movement:.0f}px, rest {still_for:.0f}s, "
                f"speed {speed_px:.1f}px/s)"
            )
            self._log(start_msg)
            try:
                self._capture_and_upload_video(self._auto_record_duration, 15, auto=False)
                self._update_state(
                    message="Motion-triggered video uploaded",
                    movement_recording=self._movement_record_state(),
                )
            except Exception as exc:
                logger.warning("Motion-triggered video failed: %s", exc)
                self._update_state(
                    message=f"Motion video failed: {exc}",
                    movement_recording=self._movement_record_state(),
                )
            finally:
                self._movement_record_active = False
                self._update_state(movement_recording=self._movement_record_state())
                self._recording_lock.release()

        self._movement_record_active = True
        threading.Thread(target=worker, name="motion-video", daemon=True).start()

    def _start_background_recording(self) -> None:
        def worker() -> None:
            if not self._recording_lock.acquire(blocking=False):
                return
            try:
                self._update_state(auto_recording=self._auto_record_state())
                self._capture_and_upload_video(self._auto_record_duration, 15, auto=True)
            except Exception as exc:
                logger.warning("Auto video failed: %s", exc)
                self._update_state(message=f"Auto video failed: {exc}")
            finally:
                self._recording_lock.release()
                self._auto_record_thread = None
                self._update_state(auto_recording=self._auto_record_state())

        self._auto_record_thread = threading.Thread(target=worker, name="auto-video", daemon=True)
        self._auto_record_thread.start()

    def _capture_and_upload_video(self, duration: float, fps: int, *, auto: bool) -> str:
        self._camera.start()
        video_path = Path(tempfile.gettempdir()) / f"pet_follower_{int(time.time())}.mp4"
        writer: Optional[cv2.VideoWriter] = None
        frames_written = 0
        start = time.monotonic()
        target = start
        try:
            while time.monotonic() - start < duration:
                frame = self._camera.get_frame(wait=True, timeout=1.0, copy_frame=True)
                if frame is None:
                    continue
                if writer is None:
                    height, width = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
                    if not writer.isOpened():
                        writer.release()
                        writer = None
                        raise RuntimeError("Unable to open video writer")
                writer.write(frame)
                frames_written += 1
                target += 1.0 / fps
                sleep_for = target - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
            if writer is None or frames_written == 0:
                raise RuntimeError("Video recording captured no frames")
        finally:
            if writer is not None:
                writer.release()
        try:
            send_video_file(video_path)
            label = "Auto video uploaded" if auto else "Video uploaded"
            if auto:
                self._last_auto_record = time.monotonic()
                self._last_auto_record_wall = time.time()
            self._update_state(message=label, auto_recording=self._auto_record_state())
            return "Automatic video uploaded" if auto else "Video clip recorded and uploaded"
        finally:
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _update_state(
        self,
        *,
        mode: Optional[str] = None,
        message: Optional[str] = None,
        target_visible: Optional[bool] = None,
        detection: Optional[Dict[str, Any]] = None,
        safety: Optional[Dict[str, Any]] = None,
        motion: Optional[Dict[str, Any]] = None,
        fps: Optional[float] = None,
        last_log: Optional[str] = None,
        auto_recording: Optional[Dict[str, Any]] = None,
        smart_snapshot: Optional[Dict[str, Any]] = None,
        movement_recording: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._state_lock:
            if mode is not None:
                self._state.mode = mode
            if message is not None:
                self._state.message = message
            if target_visible is not None:
                self._state.target_visible = target_visible
            if detection is not None:
                self._state.detection = detection
            if safety is not None:
                self._state.safety = safety
            if motion is not None:
                self._state.motion = motion
            if fps is not None:
                self._state.fps = fps
            if last_log is not None:
                self._state.last_log = last_log
            if auto_recording is not None:
                self._state.auto_recording = auto_recording
            if smart_snapshot is not None:
                self._state.smart_snapshot = smart_snapshot
            if movement_recording is not None:
                self._state.movement_recording = movement_recording
            snapshot = self._state.to_dict()
        self._events.emit({"type": "status", "data": snapshot})
