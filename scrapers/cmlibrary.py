import logging

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper
from ._common import extract_jsonld_events, extract_time, log_snapshot

log = logging.getLogger(__name__)

# CMLibrary uses BiblioCommons for events. The /v2/events page is the
# server-rendered list view (the JS app at /events is harder to parse).
EVENTS_URL = "https://cmlibrary.bibliocommons.com/v2/events"
VENUE = "Charlotte Mecklenburg Library, Charlotte NC"

# Filter out community-room rentals and kids' programs — keep adult/lit events.
KEEP_KEYWORDS = (
    "author", "book", "lecture", "talk", "discussion", "writers",
    "writing", "poetry", "verse", "vino", "literary", "speaker",
    "history", "salon", "reading", "presents", "in conversation",
)

# CMLibrary publishes hundreds of events. Cap output.
MAX_EVENTS = 12


class CMLibraryScraper(BaseScraper):
    SOURCE = "Charlotte Mecklenburg Library"

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
                page.wait_for_timeout(3000)

                events = extract_jsonld_events(page, self.SOURCE, VENUE, self._is_within_window)
                if not events:
                    # BiblioCommons-specific cards + generic fallbacks
                    selectors = (
                        ".cp-event-card, .events-card, "
                        "[data-key='event-card'], [class*='EventCard'], "
                        "article[class*='event'], li[class*='event']"
                    )
                    cards = page.locator(selectors).all()
                    if not cards:
                        log_snapshot(page, self.SOURCE)

                    for card in cards:
                        try:
                            title_el = card.locator(
                                "h2, h3, .cp-event-card-title, [class*='title']"
                            ).first
                            date_el = card.locator(
                                "time[datetime], .cp-event-date, [class*='date']"
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

        # Quality filter: keep only adult/literary programming
        events = [
            e for e in events
            if any(kw in e["title"].lower() for kw in KEEP_KEYWORDS)
        ]
        events.sort(key=lambda e: e["date"])
        events = events[:MAX_EVENTS]
        log.info("%s: found %d events (after quality filter)", self.SOURCE, len(events))
        return events
