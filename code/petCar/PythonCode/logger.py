# logger.py
"""
Member C logging module:
- append_event(description, extra): append one event to today's log (JSON Lines)
- get_today_log_structured(): return list of structured entries
- get_today_log_text(): return plain-text log for LLM analysis
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import LOG_DIR


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()


def _get_today_log_path() -> Path:
    """Return the path to today's log file (JSONL)."""
    filename = f"pet_log_{_today_str()}.jsonl"
    return LOG_DIR / filename


def append_event(description: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Append a single event to today's log file in JSON Lines format.

    Each line is a JSON object:
    {
      "time": "2025-11-23T10:15:23",
      "description": "The dog is sleeping on the sofa.",
      "extra": {...}
    }

    Args:
        description: Short natural language description of the event.
        extra: Optional dictionary for additional info (state, sensor data, etc.).
    """
    log_path = _get_today_log_path()
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "description": description,
        "extra": extra or {},
    }

    with log_path.open("a", encoding="utf-8") as f:
        json_line = json.dumps(entry, ensure_ascii=False)
        f.write(json_line + "\n")


def get_today_log_structured() -> List[Dict[str, Any]]:
    """
    Read today's log file and return a list of entries.

    Returns:
        A list of dicts, one per line in the JSONL file.
        If the log file does not exist yet, returns an empty list.
    """
    log_path = _get_today_log_path()
    if not log_path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entries.append(obj)
            except json.JSONDecodeError:
                print("[logger] Warning: skipping invalid log line:", line)

    return entries


def get_today_log_text() -> str:
    """
    Convert today's structured log into a plain-text form suitable for LLM input.

    Format example:
        10:15 The dog is sleeping on the sofa.
        11:30 The dog is playing with a ball in the living room.

    Returns:
        A multi-line string combining all events of the day.
    """
    entries = get_today_log_structured()
    lines: List[str] = []

    for e in entries:
        time_str = e.get("time", "")
        # Extract "HH:MM" from ISO datetime string
        hhmm = time_str[11:16] if len(time_str) >= 16 else time_str
        desc = e.get("description", "")
        lines.append(f"{hhmm} {desc}")

    return "\n".join(lines)
