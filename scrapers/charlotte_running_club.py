import logging
import re

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .base import BaseScraper

log = logging.getLogger(__name__)

# RunSignup's search page for Charlotte NC races — plain HTML, no JS required
SEARCH_URL = "https://runsignup.com/Races/NC/Charlotte"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


class CharlotteRunningClubScraper(BaseScraper):
    SOURCE = "Charlotte Running Club / RunSignup"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        try:
            resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # RunSignup race cards in search results
            for card in soup.select(".race-card, .race-result, [class*='race-row'], [class*='RaceRow']"):
                try:
                    title_el = card.select_one("h2, h3, h4, [class*='race-name'], [class*='RaceName']")
                    date_el = card.select_one("[class*='date'], [class*='Date'], time")

                    title_text = title_el.get_text(strip=True) if title_el else ""
                    if not title_text:
                        continue

                    date_text = date_el.get_text(strip=True) if date_el else ""
                    try:
                        event_date = dateparser.parse(date_text, fuzzy=True).date()
                    except Exception:
                        continue

                    if not self._is_within_window(event_date):
                        continue

                    location_el = card.select_one("[class*='location'], [class*='city'], [class*='venue']")
                    venue = location_el.get_text(strip=True) if location_el else "Charlotte, NC"

                    events.append({
                        "title": title_text[:100],
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": _extract_time(date_text),
                        "venue": venue[:80],
                        "raw_description": "",
                        "source": self.SOURCE,
                    })
                except Exception as exc:
                    log.debug("Card parse error: %s", exc)

        except Exception as exc:
            log.error("%s scrape failed: %s", self.SOURCE, exc)

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
