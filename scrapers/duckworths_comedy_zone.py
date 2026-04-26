import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Scrape Comedy Zone Charlotte's own website — no Ticketmaster API needed
COMEDY_ZONE_URL = "https://thecomedyzone.com/charlotte-nc/"


class DuckworthsComedyZoneScraper(BaseScraper):
    SOURCE = "The Comedy Zone"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(COMEDY_ZONE_URL, timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                for card in page.locator(
                    ".show, .event, article, [class*='show-card'], "
                    "[class*='event-card'], [class*='ShowCard']"
                ).all():
                    try:
                        title_el = card.locator("h2, h3, h4, [class*='title'], [class*='name'], [class*='performer']").first
                        date_el = card.locator("time, [class*='date'], [class*='Date'], [datetime]").first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            continue

                        date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                        date_text = date_attr or (date_el.inner_text().strip() if date_el.count() else "")
                        if not date_text:
                            continue

                        try:
                            event_date = dateparser.parse(date_text, fuzzy=True).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        time_text = _extract_time(card.inner_text())

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": time_text,
                            "venue": "Comedy Zone Charlotte, 900 NC Music Factory Blvd, Charlotte NC",
                            "raw_description": "",
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Comedy Zone card error: %s", exc)

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
