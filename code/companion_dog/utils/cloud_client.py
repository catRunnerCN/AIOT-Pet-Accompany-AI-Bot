# pet_follower/utils/cloud_client.py
from __future__ import annotations

import io
from pathlib import Path

import cv2
import requests

SERVER_IP = "34.61.99.220"  # Replace with the host that receives uploads
SERVER_IMAGE_URL = f"http://{SERVER_IP}:5000/api/upload-image"
SERVER_VIDEO_URL = f"http://{SERVER_IP}:5000/api/upload-video"


def send_frame_bgr(frame) -> None:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        print("[cloud_client] encode failed")
        return

    img_bytes = io.BytesIO(buf.tobytes())
    files = {"image": ("frame_from_pi.jpg", img_bytes, "image/jpeg")}

    try:
        resp = requests.post(SERVER_IMAGE_URL, files=files, timeout=10)
        print("[cloud_client] status:", resp.status_code)
        try:
            print("[cloud_client] json:", resp.json())
        except Exception:
            print("[cloud_client] text:", resp.text)
    except Exception as exc:
        print("[cloud_client] error:", exc)


def send_video_file(video_path) -> None:
    path = Path(video_path)
    if not path.exists():
        print(f"[cloud_client] video missing: {path}")
        return

    with path.open("rb") as fh:
        files = {"video": (path.name, fh, "video/mp4")}
        try:
            resp = requests.post(SERVER_VIDEO_URL, files=files, timeout=300)
            print("[cloud_client] video status:", resp.status_code)
            try:
                print("[cloud_client] json:", resp.json())
            except Exception:
                print("[cloud_client] text:", resp.text)
        except Exception as exc:
            print("[cloud_client] error sending video:", exc)
