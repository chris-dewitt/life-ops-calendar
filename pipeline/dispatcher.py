import logging
import os
import re
import time
from urllib.parse import urlencode

import requests

SLEEP_SECONDS = 15
TIMEOUT = 30


def _parse_time(text: str) -> tuple[int, int]:
    """Return (hour 0-23, minute 0-59). Defaults to noon on garbage input."""
    if not text or text == "TBD" or "see" in text.lower():
        return 12, 0
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", text, re.IGNORECASE)
    if not m:
        return 12, 0
    hour = int(m.group(1))
    minute = int(m.group(2))
    meridiem = m.group(3).upper()
    if meridiem == "PM" and hour != 12:
        hour += 12
    if meridiem == "AM" and hour == 12:
        hour = 0
    return hour, minute


def _build_params(event: dict) -> dict:
    date_parts = (event.get("date") or "2026-01-01").split("-")
    year = int(date_parts[0])
    month = int(date_parts[1])
    day = int(date_parts[2])
    hour, minute = _parse_time(event.get("time") or "")
    return {
        "ev_year": str(year),
        "ev_month": str(month),
        "ev_day": str(day),
        "ev_hour": str(hour),
        "ev_minute": str(minute),
        "ev_title": (event.get("title") or "Event")[:100],
        "ev_venue": (event.get("venue") or "")[:80],
        "ev_summary": (event.get("summary") or "")[:250],
    }


def dispatch(events: list[dict]) -> None:
    """One GET per event. Fields are URL params so MacroDroid binds them to globals automatically."""
    url = os.environ["MACRODROID_WEBHOOK_URL"]
    total = len(events)

    for i, event in enumerate(events, 1):
        params = _build_params(event)
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}{urlencode(params)}"

        resp = requests.get(full_url, timeout=TIMEOUT)
        resp.raise_for_status()
        logging.info("Dispatched event %d/%d: %s", i, total, params["ev_title"])

        if i < total:
            time.sleep(SLEEP_SECONDS)


def send_error(message: str) -> None:
    url = os.environ.get("MACRODROID_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(
            url,
            json={"status": "error", "message": message},
            timeout=TIMEOUT,
        )
    except Exception:
        pass
