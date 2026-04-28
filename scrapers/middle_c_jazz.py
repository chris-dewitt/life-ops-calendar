import logging
import re
from datetime import datetime

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Events archive — confirmed URL from search; /calendar was a redirect that broke
EVENTS_URL = "https://www.middlecjazz.com/events/"

# Jazz clubs publish full seasons — cap to the next N shows to avoid flooding
MAX_EVENTS = 5


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
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.wait_for_timeout(2000)

                # Primary: RHP booking system card class used by this venue
                cards = page.locator(".rhpSingleEvent").all()

                if not cards:
                    # Fallback A: WordPress post/article with date meta
                    cards = page.locator(
                        "article.type-tribe_events, "
                        ".tribe-events-calendar-list__event-article, "
                        "article[class*='event'], .event-item"
                    ).all()

                if not cards:
                    # Fallback B: any article/div containing a time element
                    cards = page.locator("article, .post").filter(
                        has=page.locator("time, [class*='date']")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        lines = [ln.strip() for ln in card.inner_text().split("\n") if ln.strip()]
                        if len(lines) < 2:
                            continue

                        # RHP layout: line 0 = date ("SUN, APR 26, 2026"),
                        # line 1 = artist/title, line 2 = "Show Xpm | Doors…"
                        date_text = lines[0]
                        title = lines[1].title()
                        time_text = lines[2] if len(lines) > 2 else ""

                        try:
                            event_date = dateparser.parse(date_text, fuzzy=True).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        time_match = re.search(
                            r"Show\s+(\d{1,2}(?::\d{2})?(?:am|pm))", time_text, re.I
                        )
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
                page.close()
                ctx.close()
                browser.close()

        events.sort(key=lambda e: e["date"])
        events = events[:MAX_EVENTS]

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _log_snapshot(page, label: str) -> None:
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot (no cards found): %s", label, text)
    except Exception:
        pass


def _normalize_time(t: str) -> str:
    try:
        return datetime.strptime(t.lower(), "%I:%M%p").strftime("%I:%M %p")
    except ValueError:
        try:
            return datetime.strptime(t.lower(), "%I%p").strftime("%I:%M %p")
        except ValueError:
            return t.upper()
