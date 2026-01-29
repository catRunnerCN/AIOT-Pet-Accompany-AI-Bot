"""Runtime configuration for the PetFollower demo."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR

@dataclass
class CameraConfig:
    device_index: int = 0
    resolution: Tuple[int, int] = (640, 480)
    fps: int = 20
    warmup_time: float = 0.8
    hflip: bool = False
    vflip: bool = False
    use_picamera2: bool = True
    picamera_format: str = "RGB888"
    use_vilib_preview: bool = False
    preview_local: bool = False
    preview_web: bool = False
    preview_show_fps: bool = True


@dataclass
class VisionConfig:
    model_path: Path = BASE_DIR / "models" / "yolov5s.torchscript"
    fallback_model: str = "yolov8n.pt"
    conf_threshold: float = 0.25
    iou_threshold: float = 0.45
    dog_class_ids: Tuple[int, ...] = (16,)
    max_detections: int = 1
    device: str | int | None = None
    use_half_precision: bool = False
    distance_gain: float = 9500.0
    min_distance_cm: float = 25.0
    max_distance_cm: float = 200.0


@dataclass
class MotionConfig:
    forward_speed: int = 35
    search_speed: int = 25
    wobble_speed: int = 30
    turn_scale: float = 25.0
    center_deadband: int = 15
    safe_distance_cm: float = 55.0
    stop_distance_cm: float = 20
    retreat_distance_cm: float = 10
    retreat_power: int = 30
    lost_target_timeout: float = 1.8
    search_pan_amplitude: int = 25
    search_interval: float = 2.0
    pursuit_hold_time: float = 0.8
    interaction_distance_cm: float = 40
    celebration_duration: float = 6.0
    celebration_cooldown: float = 10.0
    obstacle_check_interval: float = 0.2
    cliff_check_interval: float = 0.4
    enable_cliff_detection: bool = False


@dataclass
class InteractionConfig:
    random_interval_range: Tuple[float, float] = (8.0, 14.0)
    wobble_angle: int = 12
    pause_duration_range: Tuple[float, float] = (1.5, 3.0)
    tts_language: str = "en-US"
    greeting_lines: Sequence[str] = (
        "Hi buddy!",
        "Let's go for a walk.",
        "I see you!",
    )
    enable_sound: bool = True
    sound_volume: int = 45
    sound_files: List[Path] = field(default_factory=list)
    tts_probability: float = 0.5


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_path: Path = PROJECT_ROOT / "pet_follower.log"


@dataclass
class PetFollowerConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    interaction: InteractionConfig = field(default_factory=InteractionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


config = PetFollowerConfig()
