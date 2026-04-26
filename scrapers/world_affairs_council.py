import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://worldaffairscharlotte.org/events/"


class WorldAffairsCouncilScraper(BaseScraper):
    SOURCE = "World Affairs Council of Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=20000)
                # EventOn plugin loads events via AJAX — wait for cards to appear
                try:
                    page.wait_for_selector(".evcal_eventcard, .eventon_list_event", timeout=10000)
                except Exception:
                    pass

                for card in page.locator(".evcal_eventcard, .eventon_list_event").all():
                    try:
                        lines = [l.strip() for l in card.inner_text().split("\n") if l.strip()]
                        if len(lines) < 2:
                            continue

                        title_text = lines[0]
                        date_text = " ".join(lines[1:3])

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
                            "venue": "World Affairs Council of Charlotte, UNC Charlotte",
                            "raw_description": " ".join(lines),
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
