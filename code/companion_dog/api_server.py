"""FastAPI server exposing pet_follower controls for the web dashboard."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from utils.log import logger
from web.runtime import CameraManager, EventBus, PetFollowerRuntime

# GCP server configuration for activity logs
GCP_SERVER_URL = "http://34.61.99.220:5000"  # Cloud server that stores pet activity logs

app = FastAPI(title="Pet Follower Controller", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

camera_manager = CameraManager()
events = EventBus()
runtime = PetFollowerRuntime(camera_manager, events)


# execute once when starting
@app.on_event("startup")
async def startup_event() -> None:
    events.bind_loop(asyncio.get_running_loop())
    camera_manager.start()
    logger.info("Web API server started")


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    return runtime.get_status()


@app.post("/api/commands")
def api_commands(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    action = (payload.get("action") or "").lower()
    try:
        if action == "start":
            message = runtime.start_following()
        elif action == "stop":
            message = runtime.stop_following()
        elif action == "reset":
            message = runtime.reset()
        elif action == "celebrate":
            message = runtime.celebrate()
        elif action == "force_search":
            message = runtime.force_search()
        elif action == "capture_frame":
            message = runtime.capture_snapshot()
        elif action == "record_video":
            message = runtime.record_video(payload.get("duration", 10.0))
        elif action == "auto_recording":
            message = runtime.configure_auto_recording(
                enabled=payload.get("enabled"), interval=payload.get("interval")
            )
        elif action == "manual_drive":
            message = runtime.manual_drive(
                payload.get("direction", ""), payload.get("speed", 40), payload.get("duration", 0.8)
            )
        elif action == "mark_event":
            message = runtime.mark_event(payload.get("note"))
        else:
            raise ValueError("Unknown action")
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.warning("Command failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": message, "state": runtime.get_status()}


@app.get("/stream.mjpg")
def mjpeg_stream() -> StreamingResponse:
    generator = camera_manager.mjpeg_generator()
    return StreamingResponse(
        generator,
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/events")
async def sse_events() -> StreamingResponse:
    queue = events.register()

    async def event_generator():
        try:
            while True:
                payload = await queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            events.unregister(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/gcp-log")
async def api_gcp_log() -> Dict[str, Any]:
    """Proxy endpoint to fetch the latest pet log from the GCP server.

    The GCP server exposes `/api/today-log-path`, which returns JSON:
      {
        "status": "ok",
        "log_path": "logs/pet_log_YYYY-MM-DD.jsonl",
        "content": "<jsonl text>",
      }

    This endpoint forwards that response and also parses the JSONL content
    into structured entries for the dashboard UI.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GCP_SERVER_URL}/api/today-log-path")
            if resp.status_code != 200:
                logger.warning("GCP log request failed: HTTP %s", resp.status_code)
                return {
                    "status": "error",
                    "error": f"HTTP {resp.status_code}",
                }

            data = resp.json()
            log_content = data.get("content", "") or ""
            log_path = data.get("log_path", "") or ""

            # Parse JSONL into individual entries
            entries = []
            if log_content:
                lines = [line.strip() for line in log_content.split("\n") if line.strip()]
                for line in lines:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Skip invalid lines but keep going
                        logger.debug("Skipping invalid JSONL line from GCP log")

            return {
                "status": "ok",
                "log_path": log_path,
                "entries": entries,
                "content": log_content,
            }
    except httpx.TimeoutException:
        logger.warning("Timeout connecting to GCP log server at %s", GCP_SERVER_URL)
        return {
            "status": "error",
            "error": "Timeout connecting to GCP server",
        }
    except Exception as exc:  # pragma: no cover - safety
        logger.warning("Error fetching GCP log: %s", exc)
        return {
            "status": "error",
            "error": str(exc),
        }


@app.get("/api/emotion-insight")
async def api_emotion_insight() -> Dict[str, Any]:
    """Fetch the latest pet emotion analysis from the GCP server."""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GCP_SERVER_URL}/api/emotion-insight")
            if resp.status_code != 200:
                logger.warning("Emotion insight request failed: HTTP %s", resp.status_code)
                return {"status": "error", "error": f"HTTP {resp.status_code}"}

            data = resp.json()
            analysis = (
                data.get("analysis")
                or data.get("report")
                or data.get("result")
                or data.get("data")
                or {}
            )
            return {"status": "ok", "analysis": analysis, "raw": data}
    except httpx.TimeoutException:
        logger.warning("Timeout retrieving emotion insight from %s", GCP_SERVER_URL)
        return {"status": "error", "error": "Timeout connecting to GCP server"}
    except Exception as exc:  # pragma: no cover - safety
        logger.warning("Error fetching emotion insight: %s", exc)
        return {"status": "error", "error": str(exc)}


# Mount static files (must be last to not override API routes)
app.mount("/", StaticFiles(directory="web", html=True), name="static")


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Pet Follower web API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument(
        "--reload", action="store_true", help="Enable uvicorn reload (development only)"
    )
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
