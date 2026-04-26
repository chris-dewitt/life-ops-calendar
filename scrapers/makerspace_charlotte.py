import logging
import re
from datetime import date

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Scrape their Eventbrite organizer page as HTML — no API key needed
EVENTS_URL = "https://www.eventbrite.com/o/makerspace-charlotte-8173870117"


class MakerSpaceScraper(BaseScraper):
    SOURCE = "MakerSpace Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                for card in page.locator("[data-testid='event-card'], .eds-event-card, article[class*='event']").all():
                    try:
                        title_el = card.locator("h2, h3, [class*='title'], [class*='name']").first
                        date_el = card.locator("time, [class*='date'], [class*='start']").first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            continue

                        date_text = date_el.get_attribute("datetime") or date_el.inner_text().strip() if date_el.count() else ""
                        if not date_text:
                            continue

                        try:
                            event_date = dateparser.parse(date_text, fuzzy=True).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "MakerSpace Charlotte, 1216 Thomas Ave, Charlotte NC",
                            "raw_description": "",
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Card parse error: %s", exc)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                page.close()
                ctx.close()
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
