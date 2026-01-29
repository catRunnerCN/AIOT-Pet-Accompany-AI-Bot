# api_server.py
"""
Backend server for the Pet Car project.

Runs on your PC and provides HTTP APIs:

GET  /api/test
    - Health check.

POST /api/upload-image
    - form-data: image = file
    - Save image to IMAGE_DIR, call cloud_ai.describe_image(),
      append to today's log, and return the caption.

POST /api/upload-video
    - form-data: video = file
    - Save video to VIDEO_DIR, call cloud_ai.analyze_video_clip(),
      append a [video-summary] event, and return the summary.

POST /api/append-event
    - JSON body: {"description": "text", "extra": {... optional ...}}
    - Append a manual event to today's log.

GET  /api/today-log
    - Return today's log as plain text (wrapped in JSON).

GET  /api/analyze-today
    - Read today's log, call analyze_daily_log(), and return analysis.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify

from config import IMAGE_DIR, LOG_DIR
from cloud_ai import describe_image, analyze_daily_log, analyze_video_clip
from logger import append_event, get_today_log_text

# Ensure base dirs exist
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Derive VIDEO_DIR next to IMAGE_DIR/LOG_DIR
BASE_DIR = IMAGE_DIR.parent
VIDEO_DIR = BASE_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
EMOTION_INSIGHT_PATH = LOG_DIR / "latest_emotion_insight.json"

app = Flask(__name__)


# =======================
# Basic health check
# =======================

@app.route("/api/test", methods=["GET"])
def api_test():
    return jsonify({
        "status": "ok",
        "message": "Pet Car cloud API is running.",
    })


# =======================
# Upload image from Pi
# =======================

@app.route("/api/upload-image", methods=["POST"])
def api_upload_image():
    """
    Pi sends one image via multipart/form-data:
        image: file

    We:
      1. Save it to IMAGE_DIR with timestamped filename
      2. Run describe_image() to get a caption
      3. Append an [auto-image] event to today's log
      4. Return caption + saved_path
    """
    if "image" not in request.files:
        return jsonify({"error": "no 'image' field in form-data"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"from_pi_{ts}.jpg"
    save_path = IMAGE_DIR / filename

    file.save(save_path)
    print(f"[api_server] Saved image from Pi to: {save_path}")

    # Run HF caption
    caption = describe_image(str(save_path))
    print(f"[api_server] Caption: {caption}")

    # Write to today's log
    append_event(
        description=f"[auto-image] {caption}",
        extra={"source": "pi", "image_file": filename},
    )

    return jsonify({
        "status": "ok",
        "saved_path": str(save_path),
        "caption": caption,
    })


# =======================
# Upload video from Pi
# =======================

@app.route("/api/upload-video", methods=["POST"])
def api_upload_video():
    """
    Pi uploads a short video via multipart/form-data:
        video: file

    We:
      1. Save it to VIDEO_DIR
      2. Run analyze_video_clip() to summarize pet behavior in the clip
      3. Append a [video-summary] event to today's log
      4. Return summary + saved_path
    """
    if "video" not in request.files:
        return jsonify({"error": "no 'video' field in form-data"}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = Path(file.filename).suffix or ".mp4"
    filename = f"from_pi_{ts}{suffix}"
    save_path = VIDEO_DIR / filename

    file.save(save_path)
    print(f"[api_server] Saved video from Pi to: {save_path}")

    # Analyze video with OpenAI vision
    summary = analyze_video_clip(str(save_path))
    print(f"[api_server] Video summary: {summary}")

    # Append summary to today's log
    append_event(
        description=f"[video-summary] {summary}",
        extra={"source": "pi", "video_file": filename},
    )

    return jsonify({
        "status": "ok",
        "saved_path": str(save_path),
        "summary": summary,
    })


# =======================
# Append manual event
# =======================

@app.route("/api/append-event", methods=["POST"])
def api_append_event():
    """
    Append a custom event to today's log.

    JSON body:
      {
        "description": "dog is eating",
        "extra": {"food": "kibble"}
      }
    """
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    extra = data.get("extra") or {}

    if not description:
        return jsonify({"error": "description is required"}), 400

    append_event(description, extra=extra)
    print(f"[api_server] Appended event: {description!r}, extra={extra}")

    return jsonify({"status": "ok"})


# =======================
# Get today's log (plain text)
# =======================

@app.route("/api/today-log", methods=["GET"])
def api_today_log():
    """
    Return today's log as plain text, wrapped in JSON.
    """
    text = get_today_log_text()
    if not text.strip():
        return jsonify({
            "status": "ok",
            "message": "There are no pet activity records for today yet.",
            "log_text": "",
        })

    return jsonify({
        "status": "ok",
        "log_text": text,
    })


# =======================
# Analyze today's behavior
# =======================

@app.route("/api/analyze-today", methods=["GET"])
def api_analyze_today():
    """
    Read today's log (plain text) and call analyze_daily_log()
    via OpenAI. Return the analysis text.
    """
    log_text = get_today_log_text()
    if not log_text.strip():
        return jsonify({
            "status": "ok",
            "message": "There are no pet activity records for today yet.",
            "analysis": "",
        })

    analysis = analyze_daily_log(log_text)
    print("[api_server] Daily analysis length:", len(analysis))

    return jsonify({
        "status": "ok",
        "analysis": analysis,
    })


# =======================
# Latest emotion insight
# =======================

def _validate_emotion_payload(payload: dict):
    """
    Validate the cached emotion analysis payload loaded from disk.
    """
    if not isinstance(payload, dict):
        raise ValueError("Emotion insight payload is not a JSON object.")

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("Missing 'analysis' object.")

    required_fields = ["mood", "energy", "advice", "headline", "details"]
    missing = [field for field in required_fields if field not in analysis]
    if missing:
        raise ValueError(f"Missing fields in analysis: {', '.join(missing)}.")

    if "indicator" not in analysis:
        raise ValueError("Missing 'indicator' field in analysis.")

    if "confidence" not in analysis:
        raise ValueError("Missing 'confidence' field in analysis.")

    try:
        confidence_value = float(analysis["confidence"])
    except (TypeError, ValueError):
        raise ValueError("'confidence' must be a number in the range 0-1.")

    if not (0.0 <= confidence_value <= 1.0):
        raise ValueError("'confidence' must be between 0 and 1.")

    if "updated_at" not in analysis:
        raise ValueError("Missing 'updated_at' field in analysis.")

    updated_at = analysis["updated_at"]
    if not isinstance(updated_at, (int, float, str)):
        raise ValueError("'updated_at' must be a Unix timestamp or string.")

    return analysis


@app.route("/api/emotion-insight", methods=["GET"])
def api_emotion_insight():
    """
    Return the most recent emotion analysis generated by the AI pipeline.
    The data is stored on disk (latest_emotion_insight.json) for the Pi to fetch.
    """
    try:
        raw = EMOTION_INSIGHT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return jsonify({
            "status": "error",
            "error": "Emotion insight file not found. Run the analyzer first.",
        }), 404
    except OSError as exc:
        return jsonify({
            "status": "error",
            "error": f"Failed to read emotion insight file: {exc}",
        }), 500

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return jsonify({
            "status": "error",
            "error": f"Emotion insight file contains invalid JSON: {exc}",
        }), 500

    try:
        analysis = _validate_emotion_payload(payload)
    except ValueError as exc:
        return jsonify({
            "status": "error",
            "error": str(exc),
        }), 500

    return jsonify({
        "status": "ok",
        "analysis": analysis,
    })


# =======================
# Get today's log file path
# =======================

@app.route("/api/today-log-path", methods=["GET"])
def api_today_log_path():
    """
    Return the path to the log file with the newest date.
    Scans LOG_DIR for files matching pet_log_YYYY-MM-DD.jsonl pattern
    and returns the one with the most recent date.
    Format: "logs/pet_log_YYYY-MM-DD.jsonl"
    """
    # Pattern to match pet_log_YYYY-MM-DD.jsonl files
    pattern = re.compile(r"pet_log_(\d{4}-\d{2}-\d{2})\.jsonl")
    
    newest_file = None
    newest_date = None
    
    # Scan LOG_DIR for matching log files
    if LOG_DIR.exists():
        for log_file in LOG_DIR.glob("pet_log_*.jsonl"):
            match = pattern.match(log_file.name)
            if match:
                try:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if newest_date is None or file_date > newest_date:
                        newest_date = file_date
                        newest_file = log_file
                except ValueError:
                    # Skip files with invalid date format
                    continue
    
    if newest_file:
        # Read and return the log file content directly
        try:
            log_content = newest_file.read_text(encoding="utf-8")
            return jsonify({
                "status": "ok",
                "log_path": f"logs/{newest_file.name}",
                "content": log_content,
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "error": f"Failed to read log file: {str(e)}",
            }), 500
    else:
        # No log files found, return empty content
        return jsonify({
            "status": "ok",
            "log_path": None,
            "content": "",
            "message": "No existing log files found",
        })


if __name__ == "__main__":
    # host='0.0.0.0' so Pi on the same LAN can reach your PC
    app.run(host="0.0.0.0", port=5000, debug=True)
