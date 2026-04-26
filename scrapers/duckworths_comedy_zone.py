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

# Comedy Zone Charlotte — Ticketmaster venue search
COMEDY_ZONE_URL = (
    "https://app.ticketmaster.com/discovery/v2/events.json"
    "?keyword=comedy+zone+charlotte&city=Charlotte&stateCode=NC&size=20&sort=date,asc"
    "&classificationName=comedy&apikey=DpFMzKt3UazBFMnqthqBjIKqiHROvBKo"
)

# Duckworth's Charlotte — their actual website
DUCKWORTHS_URL = "https://www.duckworthscharlotte.com/events"


class DuckworthsComedyZoneScraper(BaseScraper):
    SOURCE = "Duckworth's & The Comedy Zone"

    def scrape(self) -> list[dict]:
        events: list[dict] = []
        events.extend(_scrape_comedy_zone(self._is_within_window))
        events.extend(_scrape_duckworths(self._is_within_window))
        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_comedy_zone(in_window) -> list[dict]:
    results = []
    try:
        resp = requests.get(COMEDY_ZONE_URL, headers=HEADERS, timeout=20)
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
                venue_name = (
                    ev.get("_embedded", {})
                    .get("venues", [{}])[0]
                    .get("name", "Comedy Zone Charlotte")
                )
                results.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _fmt_time(time_str),
                    "venue": f"{venue_name}, Charlotte NC",
                    "raw_description": "",
                    "source": "The Comedy Zone",
                })
            except Exception as exc:
                log.debug("Comedy Zone event error: %s", exc)
    except Exception as exc:
        log.error("Comedy Zone scrape failed: %s", exc)
    return results


def _scrape_duckworths(in_window) -> list[dict]:
    results = []
    try:
        resp = requests.get(DUCKWORTHS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for card in soup.select(".event-card, article, [class*='event']"):
            try:
                title_el = card.select_one("h2, h3, h4, [class*='title']")
                date_el = card.select_one("time, [class*='date'], [datetime]")

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
                    "venue": "Duckworth's, Charlotte NC",
                    "raw_description": "",
                    "source": "Duckworth's",
                })
            except Exception as exc:
                log.debug("Duckworth's event error: %s", exc)
    except Exception as exc:
        log.error("Duckworth's scrape failed: %s", exc)
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
