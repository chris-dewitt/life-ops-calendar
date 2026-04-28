import logging
from datetime import date, timedelta

import requests
from dateutil import parser as dateparser

from .base import BaseScraper

log = logging.getLogger(__name__)

# Legistar WebAPI — public, no auth required
# Avoid server-side OData date filters (some Legistar instances return 500);
# instead fetch the next N events sorted by date and filter client-side.
LEGISTAR_API = "https://webapi.legistar.com/v1/charlotte/Events"


class CharlotteCityCouncilScraper(BaseScraper):
    SOURCE = "Charlotte City Council"

    def scrape(self) -> list[dict]:
        events: list[dict] = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

        params = {
            "$orderby": "EventDate asc",
            "$top": "100",
        }

        try:
            resp = requests.get(LEGISTAR_API, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            for item in resp.json():
                title = item.get("EventBodyName", "").strip()
                if not title:
                    continue

                raw_date = item.get("EventDate", "")
                raw_time = item.get("EventTime", "") or "TBD"
                location = item.get("EventLocation", "") or "Charlotte City Hall, 600 East 4th Street"

                try:
                    event_date = dateparser.parse(raw_date).date()
                except Exception:
                    continue

                if not self._is_within_window(event_date):
                    continue

                events.append({
                    "title": title,
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": raw_time,
                    "venue": location,
                    "raw_description": title,
                    "source": self.SOURCE,
                })

        except Exception as exc:
            log.error("%s scrape failed: %s", self.SOURCE, exc)

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events
