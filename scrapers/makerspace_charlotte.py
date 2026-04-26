import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# MakerSpace Charlotte hosts events on Eventbrite
EVENTS_URL = "https://www.eventbrite.com/o/makerspace-charlotte-8358690135"


class MakerSpaceScraper(BaseScraper):
    SOURCE = "MakerSpace Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"})

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                cards = page.query_selector_all(
                    "[data-testid='search-event-card-wrapper'], .eds-event-card, li.search-event-card"
                )

                for card in cards:
                    try:
                        title_el = card.query_selector("h2, h3, [data-testid='event-card-title'], .eds-event-card__formatted-name")
                        date_el = card.query_selector("time, [data-testid='event-card-date'], .eds-event-card__formatted-date")
                        venue_el = card.query_selector("[data-testid='event-card-venue'], .card-text--truncated__one")
                        desc_el = card.query_selector("p, [data-testid='event-card-description']")

                        title_text = title_el.inner_text().strip() if title_el else ""
                        if not title_text:
                            continue

                        date_attr = date_el.get_attribute("datetime") if date_el else ""
                        date_text = date_attr or (date_el.inner_text() if date_el else "")
                        try:
                            event_date = dateparser.parse(date_text.strip()).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        venue_text = venue_el.inner_text().strip() if venue_el else "MakerSpace Charlotte"
                        desc_text = desc_el.inner_text().strip() if desc_el else ""

                        events.append({
                            "title": title_text,
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": venue_text or "MakerSpace Charlotte, 1216 Thomas Ave",
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
