import logging
import re

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .base import BaseScraper

log = logging.getLogger(__name__)

# Eventbrite's public search API — no auth required, no bot detection
EVENTBRITE_API = (
    "https://www.eventbrite.com/api/v3/destination/search/"
    "?q=makerspace+charlotte&place.address.city=Charlotte&place.address.region=NC"
    "&expand=event_sales_status,primary_venue,image"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.eventbrite.com/",
}


class MakerSpaceScraper(BaseScraper):
    SOURCE = "MakerSpace Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        try:
            resp = requests.get(EVENTBRITE_API, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            event_list = (
                data.get("events", {}).get("results", [])
                or data.get("results", [])
                or []
            )

            for ev in event_list:
                try:
                    title = ev.get("name", {}).get("text", "") or ev.get("name", "")
                    if not title or "makerspace" not in title.lower():
                        continue

                    start = ev.get("start", {}).get("local", "") or ev.get("start_date", "")
                    try:
                        event_date = dateparser.parse(start).date()
                    except Exception:
                        continue

                    if not self._is_within_window(event_date):
                        continue

                    venue = ev.get("primary_venue", {}).get("address", {}).get("localized_address_display", "MakerSpace Charlotte")
                    desc_html = ev.get("description", {}).get("html", "") or ""
                    desc_text = BeautifulSoup(desc_html, "lxml").get_text()[:300]

                    events.append({
                        "title": title[:100],
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": _extract_time(start),
                        "venue": venue[:80] or "MakerSpace Charlotte, 1216 Thomas Ave",
                        "raw_description": desc_text,
                        "source": self.SOURCE,
                    })
                except Exception as exc:
                    log.debug("Event parse error: %s", exc)

        except Exception as exc:
            log.error("%s scrape failed: %s", self.SOURCE, exc)

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_time(iso: str) -> str:
    m = re.search(r"T(\d{2}):(\d{2})", iso)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12:02d}:{mn:02d} {suffix}"
    return "TBD"
