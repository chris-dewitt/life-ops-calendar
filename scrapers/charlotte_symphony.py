import logging

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper
from ._common import extract_jsonld_events, extract_time, log_snapshot

log = logging.getLogger(__name__)
EVENTS_URL = "https://www.charlottesymphony.org/calendar/"
VENUE = "Knight Theater / Belk Theater, Charlotte NC"

# Symphonies publish full seasons; cap to keep the dispatch from flooding.
MAX_EVENTS = 10


class CharlotteSymphonyScraper(BaseScraper):
    SOURCE = "Charlotte Symphony Orchestra"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2500)

                events = extract_jsonld_events(page, self.SOURCE, VENUE, self._is_within_window)
                if not events:
                    selectors = (
                        ".event-card, .concert-card, .performance-card, "
                        "article[class*='event'], article[class*='concert'], "
                        "li[class*='event'], [class*='EventCard']"
                    )
                    cards = page.locator(selectors).all()
                    if not cards:
                        log_snapshot(page, self.SOURCE)

                    for card in cards:
                        try:
                            title_el = card.locator(
                                "h2, h3, h4, [class*='title'], [class*='Title']"
                            ).first
                            date_el = card.locator(
                                "time[datetime], [class*='date'], [class*='Date']"
                            ).first

                            title = title_el.inner_text().strip() if title_el.count() else ""
                            if not title:
                                continue

                            date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                            date_text = date_attr or (
                                date_el.inner_text().strip() if date_el.count() else ""
                            )
                            if not date_text:
                                continue

                            try:
                                event_date = dateparser.parse(date_text, fuzzy=True).date()
                            except Exception:
                                continue

                            if not self._is_within_window(event_date):
                                continue

                            events.append({
                                "title": title[:100],
                                "date": event_date.strftime("%Y-%m-%d"),
                                "time": extract_time(date_text),
                                "venue": VENUE,
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

        events.sort(key=lambda e: e["date"])
        events = events[:MAX_EVENTS]
        log.info("%s: found %d events", self.SOURCE, len(events))
        return events
