import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://www.independentpicturehouse.org/films/"


class IndependentPictureHouseScraper(BaseScraper):
    SOURCE = "The Independent Picture House"

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
                    ".film-card, .movie-listing, article, .wp-block-post, .entry"
                )

                for card in cards:
                    try:
                        title_el = card.query_selector("h2, h3, h4, .film-title, .entry-title")
                        date_el = card.query_selector("time, .screening-date, [class*='date'], [class*='showtime']")
                        desc_el = card.query_selector("p, .film-description, .entry-content")

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

                        desc_text = desc_el.inner_text().strip() if desc_el else ""

                        events.append({
                            "title": title_text,
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "The Independent Picture House, 3200 N Davidson St",
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
