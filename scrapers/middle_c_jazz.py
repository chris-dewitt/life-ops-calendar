import logging
import re
from datetime import datetime

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://www.middlecjazz.com/calendar"


class MiddleCJazzScraper(BaseScraper):
    SOURCE = "Middle C Jazz"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                for card in page.locator(".rhpSingleEvent").all():
                    try:
                        lines = [l.strip() for l in card.inner_text().split("\n") if l.strip()]
                        if len(lines) < 2:
                            continue

                        # Line 0: "SUN, APR 26, 2026"  Line 1: title  Line 2: "Show 1pm | Doors..."
                        date_text = lines[0]
                        title = lines[1].title()
                        time_text = lines[2] if len(lines) > 2 else ""

                        try:
                            event_date = dateparser.parse(date_text).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        time_match = re.search(r"Show\s+(\d{1,2}(?::\d{2})?(?:am|pm))", time_text, re.I)
                        time_fmt = _normalize_time(time_match.group(1)) if time_match else "TBD"

                        events.append({
                            "title": title[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": time_fmt,
                            "venue": "Middle C Jazz, 300 W Tremont Ave, Charlotte NC",
                            "raw_description": time_text,
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


def _normalize_time(t: str) -> str:
    try:
        return datetime.strptime(t.lower(), "%I:%M%p").strftime("%I:%M %p")
    except ValueError:
        try:
            return datetime.strptime(t.lower(), "%I%p").strftime("%I:%M %p")
        except ValueError:
            return t.upper()
