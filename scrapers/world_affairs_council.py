import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://worldaffairscharlotte.org/events/"

# The Events Calendar (tribe) and EventOn (evcal) are the two most common WP
# calendar plugins.  Include all known class variants for both.
_CARD_SEL = (
    # Tribe Events Calendar list view (most common for nonprofits on WP)
    ".tribe-events-calendar-list__event-article, "
    ".tribe-events-calendar-list__event, "
    "article.tribe_events_cat, .tribe-event, "
    # EventOn plugin
    ".evcal_eventcard, .eventon_list_event, "
    # Generic fallbacks
    "article[class*='event'], li[class*='event']"
)
_FALLBACK_SEL = (
    "article, .event, [class*='event-card'], [class*='EventCard'], "
    "[class*='event-item'], [class*='EventItem']"
)


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

                # Scroll to trigger any lazy-loaded events
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(1000)

                # Wait for known card selectors
                try:
                    page.wait_for_selector(_CARD_SEL, timeout=12000)
                except Exception:
                    log.debug("%s: primary selectors not found, trying fallback", self.SOURCE)

                cards = page.locator(_CARD_SEL).all()

                if not cards:
                    cards = page.locator(_FALLBACK_SEL).filter(
                        has=page.locator("time, [class*='date'], [class*='Date']")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        # Prefer <time datetime="..."> for reliable date parsing
                        time_el = card.locator("time[datetime]").first
                        if time_el.count():
                            date_attr = time_el.get_attribute("datetime") or ""
                            date_text = date_attr
                        else:
                            date_el = card.locator(
                                "[class*='date'], [class*='Date'], "
                                "[class*='tribe-event-date'], .evcal_date"
                            ).first
                            date_text = date_el.inner_text().strip() if date_el.count() else ""

                        if not date_text:
                            continue

                        try:
                            event_date = dateparser.parse(date_text, fuzzy=True).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        title_el = card.locator(
                            "h2, h3, h4, "
                            "[class*='title'], [class*='Title'], "
                            "[class*='tribe-event-title'], .evcal_event_title"
                        ).first
                        title_text = title_el.inner_text().strip() if title_el.count() else ""

                        if not title_text:
                            lines = [
                                ln.strip()
                                for ln in card.inner_text().split("\n")
                                if ln.strip()
                            ]
                            title_text = lines[0] if lines else ""

                        if not title_text:
                            continue

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "World Affairs Council of Charlotte",
                            "raw_description": card.inner_text().strip()[:200],
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
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text, re.I)
    if m:
        return m.group(0).upper()
    m = re.search(r"T(\d{2}):(\d{2})", text)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        suffix = "AM" if h < 12 else "PM"
        return f"{h % 12 or 12:02d}:{mn} {suffix}"
    return "TBD"
