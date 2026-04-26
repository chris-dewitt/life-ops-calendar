import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Comedy Zone Charlotte uses Eventbrite; Duckworth's events are on their site
VENUES = [
    {
        "name": "The Comedy Zone Charlotte",
        "url": "https://www.eventbrite.com/o/the-comedy-zone-7619348935",
        "address": "The Comedy Zone, 900 NC Music Factory Blvd, Charlotte NC",
        "type": "eventbrite",
    },
    {
        "name": "Duckworth's",
        "url": "https://www.duckworthspub.com/events",
        "address": "Duckworth's, Charlotte NC",
        "type": "generic",
    },
]


class DuckworthsComedyZoneScraper(BaseScraper):
    SOURCE = "Duckworth's & The Comedy Zone"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for venue in VENUES:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"})
                try:
                    page.goto(venue["url"], timeout=30000)
                    page.wait_for_load_state("domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)

                    if venue["type"] == "eventbrite":
                        cards = page.locator(
                            "[data-testid='search-event-card-wrapper'], .eds-event-card"
                        ).all()
                    else:
                        cards = page.locator(
                            ".event-card, article, [class*='event-'], li.event"
                        ).all()

                    for card in cards:
                        try:
                            title_el = card.locator("h2, h3, [data-testid='event-card-title'], [class*='title']").first
                            date_el = card.locator("time, [data-testid='event-card-date'], [class*='date']").first

                            title_text = title_el.inner_text().strip() if title_el.count() else ""
                            if not title_text:
                                continue

                            date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                            date_text = date_attr or (date_el.inner_text() if date_el.count() else "")
                            try:
                                event_date = dateparser.parse(date_text.strip()).date()
                            except Exception:
                                continue

                            if not self._is_within_window(event_date):
                                continue

                            events.append({
                                "title": title_text[:100],
                                "date": event_date.strftime("%Y-%m-%d"),
                                "time": _extract_time(date_text),
                                "venue": venue["address"],
                                "raw_description": "",
                                "source": self.SOURCE,
                            })
                        except Exception as exc:
                            log.debug("Card error (%s): %s", venue["name"], exc)

                except Exception as exc:
                    log.error("%s (%s) failed: %s", self.SOURCE, venue["name"], exc)
                finally:
                    page.close()

            browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
