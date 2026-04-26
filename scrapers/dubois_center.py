import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
# UNC Charlotte's main events calendar — Dubois Center events appear here
EVENTS_URL = "https://www.charlotte.edu/events/"


class DuboisCenterScraper(BaseScraper):
    SOURCE = "Dubois Center at UNC Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)

                # UNC Charlotte events use a Localist calendar
                for card in page.locator(".em-card, .event-card, article, [class*='event']").all():
                    try:
                        title_el = card.locator("h2, h3, h4, [class*='title']").first
                        date_el = card.locator("time, [class*='date'], [datetime]").first
                        desc_el = card.locator("p, [class*='description']").first

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

                        desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "UNC Charlotte / Dubois Center",
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
