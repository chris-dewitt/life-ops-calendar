import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
# Correct URL - waccharlotte.org does not resolve
EVENTS_URL = "https://worldaffairscharlotte.org/events/"


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
                page.wait_for_timeout(3000)  # EventOn plugin loads via AJAX

                # EventOn plugin classes: .evcal_eventcard, .eventon_list_event
                for card in page.locator(".evcal_eventcard, .eventon_list_event").all():
                    try:
                        title_el = card.locator(".evcal_evdata_cell .evcal_event_title, .evo_event_title, h3, h4").first
                        date_el = card.locator(".evcal_month_line, .evo_date, [class*='date'], time").first
                        desc_el = card.locator(".evcal_desc, p").first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            # Fallback: grab all text and use first meaningful line
                            all_text = card.inner_text().strip()
                            lines = [l.strip() for l in all_text.split("\n") if l.strip()]
                            title_text = lines[0] if lines else ""

                        if not title_text:
                            continue

                        date_text = date_el.inner_text().strip() if date_el.count() else ""
                        try:
                            event_date = dateparser.parse(date_text).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "World Affairs Council of Charlotte, UNC Charlotte",
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
