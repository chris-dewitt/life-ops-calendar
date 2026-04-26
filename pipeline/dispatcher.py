import logging
import math
import os
import time

import requests

CHUNK_SIZE = 5
SLEEP_SECONDS = 15
TIMEOUT = 30


def dispatch(events: list[dict]) -> None:
    """POST events to MacroDroid in chunks of 5 with 15s throttle between chunks."""
    url = os.environ["MACRODROID_WEBHOOK_URL"]
    total_chunks = math.ceil(len(events) / CHUNK_SIZE)

    for i, start in enumerate(range(0, len(events), CHUNK_SIZE), 1):
        chunk = events[start : start + CHUNK_SIZE]
        payload = {
            "source": "autonomous_event_scraper",
            "status": "success",
            "data_chunk_id": f"{i}_of_{total_chunks}",
            "events": chunk,
        }
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        logging.info("Dispatched chunk %d/%d (%d events)", i, total_chunks, len(chunk))

        if i < total_chunks:
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
