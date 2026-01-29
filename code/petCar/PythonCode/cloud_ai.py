import base64
import time
from typing import List, Optional

import cv2
import requests
from openai import OpenAI

import config

# ========== Load config safely ==========

HF_API_KEY: Optional[str] = getattr(config, "HF_API_KEY", None)
HF_IMAGE_MODEL_URL: Optional[str] = getattr(config, "HF_IMAGE_MODEL_URL", None)

OPENAI_API_KEY: Optional[str] = getattr(config, "OPENAI_API_KEY", None)
OPENAI_TEXT_MODEL: str = getattr(config, "OPENAI_TEXT_MODEL", "gpt-4o-mini")

# ========== Initialize OpenAI client ==========

if not OPENAI_API_KEY:
    print("[cloud_ai] WARNING: OPENAI_API_KEY is not set. "
          "The OpenAI client will fall back to environment variables.")

client = OpenAI(api_key=OPENAI_API_KEY)


# ========== Image captioning: Hugging Face ==========

def describe_image(image_path: str, max_retries: int = 3) -> str:
    """
    Use an OpenAI vision-capable model (e.g., gpt-4o / gpt-4o-mini)
    to generate a caption for a single image.

    This no longer depends on Hugging Face; it only needs OPENAI_API_KEY.
    """
    if not OPENAI_API_KEY:
        return "Image captioning is not available because OPENAI_API_KEY is not configured."

    import os
    import base64

    if not os.path.exists(image_path):
        return f"Image not found: {image_path}"

    # Read image and encode as base64
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    b64_str = base64.b64encode(img_bytes).decode("utf-8")

    # Build multimodal content: one text + one image
    content_blocks = [
        {
            "type": "text",
            "text": (
                "You are an assistant that describes images of pets.\n"
                "Please give a short English sentence describing what is in the image, "
                "focusing on the main animal (e.g., dog or cat) and its obvious action "
                "or pose. Do NOT add extra analysis or advice, just one concise caption."
            ),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64_str}"
            },
        },
    ]

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_TEXT_MODEL,  # e.g., "gpt-4o-mini" or "gpt-4o"
                messages=[
                    {
                        "role": "user",
                        "content": content_blocks,
                    }
                ],
                timeout=60,
            )
            caption = resp.choices[0].message.content.strip()
            return caption
        except Exception as e:
            print(f"[cloud_ai] OpenAI error in describe_image (attempt {attempt}): {e}")
            last_error = e
            time.sleep(3)

    return (
        "Image captioning failed after multiple attempts. "
        + (f"Last error: {last_error}" if last_error else "")
    )


# ========== Daily text log → behavioral summary (OpenAI text) ==========

def analyze_daily_log(log_text: str, max_retries: int = 3) -> str:
    """
    Use an OpenAI text model (e.g., gpt-4o, gpt-4o-mini) to summarize
    a pet's daily activity log.

    Args:
        log_text: Plain-text log, one activity per line.
        max_retries: How many times to retry on transient errors.

    Returns:
        A short English summary describing:
          1) What the pet roughly did today;
          2) Whether the behavior/emotion looks normal or possibly abnormal;
          3) A short suggestion for the owner.
    """
    if not log_text.strip():
        return "There are no pet activity records for today yet."

    prompt = (
        "You are given a log of a pet's activities for a single day.\n"
        "Please do the following in English:\n"
        "1. Briefly summarize what the pet did today.\n"
        "2. Comment on whether the pet's mood and behavior seem roughly normal, "
        "   or if there are any signs of possible issues (e.g., lethargy, lack of appetite).\n"
        "3. Give one short, practical suggestion for the owner (for example, "
        "   spend more play time, pay attention to drinking water, consider a vet visit, etc.).\n\n"
        "=== TODAY'S ACTIVITY LOG ===\n"
        f"{log_text}\n"
        "===========================\n"
        "Keep your answer concise, in a few short paragraphs."
    )

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_TEXT_MODEL,  # e.g. "gpt-4o-mini" or "gpt-4o"
                messages=[
                    {
                        "role": "system",
                        "content": "You are a gentle and helpful pet behavior analyst.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                timeout=60,
            )
            content = resp.choices[0].message.content.strip()
            return content

        except Exception as e:
            print(f"[cloud_ai] OpenAI error in analyze_daily_log (attempt {attempt}): {e}")
            # Basic backoff for transient issues
            time.sleep(5)

    return "Daily behavior analysis failed. Please try again later."


# ========== Video frame extraction: OpenCV ==========

def extract_video_frames_b64(
    video_path: str,
    target_fps: float = 1.0,
    max_frames: int = 8,
) -> List[str]:
    """
    Extract frames from a video file and encode them as Base64-encoded JPGs.

    Args:
        video_path: Local video file path (e.g., .mp4).
        target_fps: Approximate sampling rate (e.g., 1.0 = 1 frame per second).
        max_frames: Maximum number of frames to extract.

    Returns:
        A list of base64-encoded JPEG strings:
        ["base64_of_frame1", "base64_of_frame2", ...]
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if not video_fps or video_fps <= 0:
        video_fps = 25.0  # Fallback FPS

    # Sample one frame every N frames
    frame_interval = max(int(video_fps // target_fps), 1)

    frames_b64: List[str] = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                frame_idx += 1
                continue
            jpg_bytes = buf.tobytes()
            b64_str = base64.b64encode(jpg_bytes).decode("utf-8")
            frames_b64.append(b64_str)

            if len(frames_b64) >= max_frames:
                break

        frame_idx += 1

    cap.release()
    return frames_b64


# ========== Video → behavior description (OpenAI vision) ==========

def analyze_video_clip(video_path: str, max_retries: int = 3) -> str:
    """
    Use an OpenAI vision-capable model to analyze a short pet video.

    Steps:
        1. Use OpenCV to extract several frames and convert them to Base64.
        2. Send the frames as image_url blocks in a single chat request.
        3. Ask the model to describe what the pet is doing overall.

    Args:
        video_path: Local video file path.
        max_retries: How many times to retry on transient errors.

    Returns:
        A short English description of what happens in the video
        and what the pet is doing.
    """
    frames_b64 = extract_video_frames_b64(
        video_path,
        target_fps=1.0,   # 1 frame per second
        max_frames=8,     # up to 8 frames
    )
    if not frames_b64:
        return "No frames could be extracted from the video."

    # Build a multimodal user message: one text block + multiple image blocks
    content_blocks = [
        {
            "type": "text",
            "text": (
                "You are a pet activity recorder creating daily logs for pet owners. "
                "These images are key frames extracted in time order from the same video. "
                "Please view them as a continuous scene and describe what is happening overall. "
                "No more than 80 words."
            ),
        }
    ]

    for b64 in frames_b64:
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                },
            }
        )

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o",  # or another vision-capable model
                messages=[
                    {
                        "role": "user",
                        "content": content_blocks,
                    }
                ],
                timeout=120,
            )
            text = resp.choices[0].message.content.strip()
            return text

        except Exception as e:
            print(f"[cloud_ai] OpenAI error in analyze_video_clip (attempt {attempt}): {e}")
            time.sleep(5)

    return "Video behavior analysis failed. Please try again later."


# ========== Simple self-test ==========

if __name__ == "__main__":
    test_video = "videos/dog_play_ball.mp4"
    print("Testing video analysis on:", test_video)
    result = analyze_video_clip(test_video)
    print("Result:\n", result)
