import logging
import re

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .base import BaseScraper

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Fillmore Charlotte — Ticketmaster venue search (JSON endpoint)
FILLMORE_URL = (
    "https://app.ticketmaster.com/discovery/v2/events.json"
    "?venueId=KovZpZAEdFaA&countryCode=US&size=20&sort=date,asc"
    "&apikey=DpFMzKt3UazBFMnqthqBjIKqiHROvBKo"
)

# Snug Harbor Charlotte — use their Songkick page (public, no auth)
SNUG_URL = "https://www.songkick.com/venues/4036864-snug-harbor/calendar"


class SnugHarborFillmoreScraper(BaseScraper):
    SOURCE = "Snug Harbor & The Fillmore"

    def scrape(self) -> list[dict]:
        events: list[dict] = []
        events.extend(_scrape_fillmore(self._is_within_window))
        events.extend(_scrape_snug(self._is_within_window))
        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_fillmore(in_window) -> list[dict]:
    results = []
    try:
        resp = requests.get(FILLMORE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        for ev in data.get("_embedded", {}).get("events", []):
            try:
                title = ev.get("name", "")
                start = ev.get("dates", {}).get("start", {}).get("localDate", "")
                time_str = ev.get("dates", {}).get("start", {}).get("localTime", "")
                if not title or not start:
                    continue
                event_date = dateparser.parse(start).date()
                if not in_window(event_date):
                    continue
                results.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _fmt_time(time_str),
                    "venue": "The Fillmore Charlotte, 820 Hamilton St, Charlotte NC",
                    "raw_description": ev.get("info", ""),
                    "source": "The Fillmore Charlotte",
                })
            except Exception as exc:
                log.debug("Fillmore event error: %s", exc)
    except Exception as exc:
        log.error("Fillmore scrape failed: %s", exc)
    return results


def _scrape_snug(in_window) -> list[dict]:
    results = []
    try:
        resp = requests.get(SNUG_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for card in soup.select(".event-listings .event, li.event, [class*='event-listing']"):
            try:
                title_el = card.select_one("strong, h3, .event-name, [class*='name']")
                date_el = card.select_one("time, [datetime], [class*='date']")

                title_text = title_el.get_text(strip=True) if title_el else ""
                if not title_text:
                    continue

                date_attr = date_el.get("datetime", "") if date_el else ""
                date_text = date_attr or (date_el.get_text(strip=True) if date_el else "")
                try:
                    event_date = dateparser.parse(date_text, fuzzy=True).date()
                except Exception:
                    continue

                if not in_window(event_date):
                    continue

                results.append({
                    "title": title_text[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(date_text),
                    "venue": "Snug Harbor, Charlotte NC",
                    "raw_description": "",
                    "source": "Snug Harbor",
                })
            except Exception as exc:
                log.debug("Snug Harbor event error: %s", exc)
    except Exception as exc:
        log.error("Snug Harbor scrape failed: %s", exc)
    return results


def _fmt_time(t: str) -> str:
    if not t:
        return "TBD"
    try:
        from datetime import datetime
        return datetime.strptime(t, "%H:%M:%S").strftime("%I:%M %p")
    except Exception:
        return t


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
