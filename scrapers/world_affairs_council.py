import logging
import re
from datetime import date

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://www.waccharlotte.org/events"


class WorldAffairsCouncilScraper(BaseScraper):
    SOURCE = "World Affairs Council of Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"})

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                # WAC uses a standard events listing; grab each event card
                cards = page.query_selector_all(".eventlist-event, .event-item, article.event, .tribe-event")
                if not cards:
                    # Fallback: grab any heading + date pairs
                    cards = page.query_selector_all("[class*='event']")

                for card in cards:
                    try:
                        title_el = card.query_selector("h2, h3, h4, .eventlist-title, .tribe-event-title")
                        date_el = card.query_selector("time, .eventlist-datetag, .tribe-event-schedule-details, [class*='date']")
                        venue_el = card.query_selector(".eventlist-venue, .tribe-venue, [class*='venue'], [class*='location']")
                        desc_el = card.query_selector("p, .eventlist-description, .tribe-event-description")

                        title_text = title_el.inner_text().strip() if title_el else ""
                        if not title_text:
                            continue

                        date_text = date_el.get_attribute("datetime") or date_el.inner_text() if date_el else ""
                        try:
                            event_date = dateparser.parse(date_text.strip()).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        venue_text = venue_el.inner_text().strip() if venue_el else "Charlotte, NC"
                        desc_text = desc_el.inner_text().strip() if desc_el else ""

                        events.append({
                            "title": title_text,
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": venue_text,
                            "raw_description": desc_text,
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Card parse error: %s", exc)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
