# config.py
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Try loading `.env` from the package directory, then project root, then fallback
env_candidates = [BASE_DIR / ".env", BASE_DIR.parent / ".env"]
for env_path in env_candidates:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

LOG_DIR = BASE_DIR / "logs"
IMAGE_DIR = BASE_DIR / "images"
VIDEO_DIR = BASE_DIR / "videos"

LOG_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
HF_API_KEY = os.getenv("HF_API_KEY", "")

if not OPENAI_API_KEY:
    print("[config] WARNING: OPENAI_API_KEY not set")
