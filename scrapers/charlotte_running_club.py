import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
# RunSignup search for Charlotte-area races
EVENTS_URL = "https://runsignup.com/Races/NC/Charlotte"


class CharlotteRunningClubScraper(BaseScraper):
    SOURCE = "Charlotte Running Club / RunSignup"

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
                    ".race-card, .race-row, .search-result-item, [class*='race-']"
                )

                for card in cards:
                    try:
                        title_el = card.query_selector("h2, h3, h4, .race-name, [class*='race-title']")
                        date_el = card.query_selector("time, .race-date, [class*='date']")
                        venue_el = card.query_selector(".race-location, [class*='location'], [class*='city']")
                        desc_el = card.query_selector("p, .race-description")

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
