import logging
import os
import time

import requests

SLEEP_SECONDS = 15
TIMEOUT = 30


def dispatch(events: list[dict]) -> None:
    """POST one event per request so MacroDroid needs no loop logic."""
    url = os.environ["MACRODROID_WEBHOOK_URL"]
    total = len(events)

    for i, event in enumerate(events, 1):
        payload = {
            "source": "autonomous_event_scraper",
            "status": "success",
            "event_num": f"{i}_of_{total}",
            "event": event,
        }
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        logging.info("Dispatched event %d/%d: %s", i, total, event.get("title", ""))

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
