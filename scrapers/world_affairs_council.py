import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://worldaffairscharlotte.org/events/"

# EventOn (evcal) and The Events Calendar (tribe) are the two most common WP calendar plugins
_CARD_SEL = (
    ".evcal_eventcard, .eventon_list_event, "
    ".tribe-event-calendar-month__calendar-event, .tribe-events-calendar-list__event-article, "
    "article.tribe_events_cat, .tribe_events_cat"
)
_FALLBACK_SEL = "article, .event, [class*='event-card'], [class*='EventCard']"


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
                # networkidle ensures AJAX calendar requests finish
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)

                # Give JS calendar extra time to render
                try:
                    page.wait_for_selector(_CARD_SEL, timeout=15000)
                except Exception:
                    log.debug("Primary selectors not found, trying fallback")

                cards = page.locator(_CARD_SEL).all()
                if not cards:
                    cards = page.locator(_FALLBACK_SEL).filter(
                        has=page.locator("time, [class*='date'], [class*='Date']")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        lines = [ln.strip() for ln in card.inner_text().split("\n") if ln.strip()]
                        if len(lines) < 2:
                            continue

                        title_text = lines[0]
                        date_text = " ".join(lines[1:4])

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
                            "venue": "World Affairs Council of Charlotte",
                            "raw_description": " ".join(lines),
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


def _log_snapshot(page, label: str) -> None:
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot (no cards found): %s", label, text)
    except Exception:
        pass


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
