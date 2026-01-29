"""Computer vision utilities for detecting dogs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import time

from .config import config
from .log import logger

try:  # pragma: no cover - hardware dependency
    from picamera2 import Picamera2
except ImportError:  # pragma: no cover
    Picamera2 = None

try:  # pragma: no cover - hardware dependency
    from ultralytics import YOLO
except ImportError:  # pragma: no cover - best effort fallback
    YOLO = None


@dataclass
class DetectionResult:
    center: Tuple[float, float]
    bbox: Tuple[float, float, float, float]
    confidence: float
    frame_size: Tuple[int, int]
    approx_distance_cm: Optional[float] = None


class CameraStream:
    """Configurable OpenCV camera stream that mirrors Vilib defaults."""

    def __init__(self) -> None:
        self.cfg = config.camera
        self.cap: Optional[cv2.VideoCapture] = None
        self._picam2: Optional["Picamera2"] = None  # type: ignore[name-defined]
        self._using_picamera2 = False
        self._preview_started = False
        self._color_order: Optional[str] = None

    def start(self) -> None:
        """Open the video device and optionally kick off the Vilib preview."""

        if self.cfg.use_picamera2 and Picamera2 is not None:
            self._start_picamera2()
            return

        if self.cfg.use_vilib_preview and not self._preview_started:
            try:
                from vilib import Vilib  # type: ignore

                Vilib.camera_start(vflip=self.cfg.vflip, hflip=self.cfg.hflip)
                if self.cfg.preview_show_fps:
                    Vilib.show_fps()
                Vilib.display(local=self.cfg.preview_local, web=self.cfg.preview_web)
                self._preview_started = True
                logger.info("Vilib camera preview started")
            except Exception as exc:  # pragma: no cover - hardware only
                logger.warning("Unable to start Vilib preview: %s", exc)

        self._start_opencv_capture()

    def _start_picamera2(self) -> None:
        if Picamera2 is None:  # pragma: no cover - safety
            raise RuntimeError("Picamera2 is not available")
        self._picam2 = Picamera2()
        config = self._picam2.create_preview_configuration(
            main={"size": tuple(self.cfg.resolution), "format": self.cfg.picamera_format}
        )
        self._picam2.configure(config)
        self._picam2.start()
        time.sleep(self.cfg.warmup_time)
        self._using_picamera2 = True
        logger.info(
            "Picamera2 started with resolution %sx%s format=%s",
            self.cfg.resolution[0],
            self.cfg.resolution[1],
            self.cfg.picamera_format,
        )

    def _start_opencv_capture(self) -> None:
        self.cap = cv2.VideoCapture(self.cfg.device_index, cv2.CAP_V4L2)
        width, height = self.cfg.resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        time.sleep(self.cfg.warmup_time)
        logger.info(
            "Camera opened on index %s with %sx%s @ %sfps",
            self.cfg.device_index,
            width,
            height,
            self.cfg.fps,
        )

    def read(self):
        if not self._using_picamera2 and self.cap is None:
            self.start()

        if self._using_picamera2:
            assert self._picam2 is not None
            frame = self._picam2.capture_array()
            if frame is None:
                logger.warning("Picamera2 capture returned None")
                return None
        else:
            assert self.cap is not None  # for mypy
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("Camera frame grab failed")
                return None
        
        # Debug log to verify function call
        # logger.debug("Processing frame in read()")
        frame = self._ensure_bgr(frame)
        
        if self.cfg.hflip:
            frame = cv2.flip(frame, 1)
        if self.cfg.vflip:
            frame = cv2.flip(frame, 0)
        return frame

    def _ensure_bgr(self, frame):
        # PASS-THROUGH: Do not swap. 
        # If camera is BGR and display is BGR, this should work.
        return frame

    def _infer_color_order(self, frame) -> str:
        return "rgb"

    def stop(self) -> None:
        if self._using_picamera2 and self._picam2 is not None:
            self._picam2.stop()
            self._picam2.close()
            self._picam2 = None
            self._using_picamera2 = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self._preview_started:
            try:
                from vilib import Vilib  # type: ignore

                Vilib.camera_close()
            except Exception:  # pragma: no cover - best effort
                pass
            self._preview_started = False
        logger.info("Camera stopped")


class DogDetector:
    """YOLO based detector that returns the most confident dog bounding box."""

    def __init__(self) -> None:
        self.cfg = config.vision
        self.model = self._load_model()

    def _load_model(self):  # pragma: no cover - heavy init
        if YOLO is None:
            logger.error(
                "The ultralytics package is not available. Run 'pip install ultralytics'."
            )
            return None
        model_path = self.cfg.model_path
        model_source = model_path if model_path.exists() else self.cfg.fallback_model
        logger.info("Loading YOLO model from %s", model_source)
        return YOLO(str(model_source))

    def detect_dog(self, frame) -> Optional[DetectionResult]:
        if self.model is None or frame is None:
            return None
        results = self.model.predict(
            frame,
            conf=self.cfg.conf_threshold,
            iou=self.cfg.iou_threshold,
            classes=list(self.cfg.dog_class_ids), # change here to detect other animals
            device=self.cfg.device,
            half=self.cfg.use_half_precision,
            verbose=False,
            max_det=self.cfg.max_detections,
        )
        if not results:
            return None
        frame_height, frame_width = frame.shape[:2]
        for prediction in results:
            boxes = getattr(prediction, "boxes", None)
            if boxes is None or len(boxes) == 0:
                continue
            top_box = boxes[0]
            x1, y1, x2, y2 = top_box.xyxy[0].tolist()
            confidence = float(top_box.conf[0])
            bbox_height = max(y2 - y1, 1.0)
            approx_distance = self._estimate_distance(bbox_height)
            detection = DetectionResult(
                center=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                bbox=(x1, y1, x2, y2),
                confidence=confidence,
                frame_size=(frame_height, frame_width),
                approx_distance_cm=approx_distance,
            )
            logger.debug("Dog detected @ %s conf=%.2f", detection.center, confidence)
            return detection
        return None

    def _estimate_distance(self, bbox_height: float) -> Optional[float]:
        if bbox_height <= 0:
            return None
        approx = self.cfg.distance_gain / bbox_height
        approx = min(max(approx, self.cfg.min_distance_cm), self.cfg.max_distance_cm)
        return approx


class ColorDetector:
    """Just for testing."""

    def __init__(self) -> None:
        # Red spans both low and high hue values, so use two intervals.
        self.lower_red1 = (0, 120, 70)
        self.upper_red1 = (10, 255, 255)
        self.lower_red2 = (170, 120, 70)
        self.upper_red2 = (180, 255, 255)
        self.min_area = 100  # Minimum contour area to consider
        self.cfg = config.vision
        self.model = "fake_model"

    def detect_dog(self, frame) -> Optional[DetectionResult]:
        """Detect the largest red area in the frame."""
        if frame is None:
            return None

        # Convert BGR to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Create mask for red color (two ranges)
        mask1 = cv2.inRange(hsv, self.lower_red1, self.upper_red1)
        mask2 = cv2.inRange(hsv, self.lower_red2, self.upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Find the largest contour
        largest_contour = max(contours, key=cv2.contourArea)

        # Check if area is large enough
        area = cv2.contourArea(largest_contour)
        if area < self.min_area:
            return None

        # Get bounding box
        x, y, w, h = cv2.boundingRect(largest_contour)
        x1, y1 = float(x), float(y)
        x2, y2 = float(x + w), float(y + h)

        # Calculate center
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0

        # Calculate confidence based on area (normalized to frame size)
        frame_height, frame_width = frame.shape[:2]
        frame_area = frame_width * frame_height
        confidence = min(area / frame_area * 10.0, 1.0)  # Scale and cap at 1.0

        # Estimate distance (fixed at 20cm)
        approx_distance = self._estimate_distance()

        detection = DetectionResult(
            center=(center_x, center_y),
            bbox=(x1, y1, x2, y2),
            confidence=confidence,
            frame_size=(frame_height, frame_width),
            approx_distance_cm=approx_distance,
        )
        logger.debug("Red detected @ %s conf=%.2f", detection.center, confidence)
        return detection

    def _estimate_distance(self) -> float:
        """Return fixed distance of 20cm."""
        return 50


__all__ = ["CameraStream", "DogDetector", "ColorDetector", "DetectionResult"]
