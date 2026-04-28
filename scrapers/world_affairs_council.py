import logging
import re
from datetime import date

import requests
from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Confirmed event listing URL — site uses /current-events/, not /events/
EVENTS_URL = "https://worldaffairscharlotte.org/current-events/"
# The Events Calendar (Tribe) REST API — enabled by default on this WP site
TRIBE_API = "https://worldaffairscharlotte.org/wp-json/tribe/events/v1/events"

_CARD_SEL = (
    ".tribe-events-calendar-list__event-article, "
    ".tribe-events-calendar-list__event, "
    "article.tribe_events_cat, .tribe-event, "
    ".evcal_eventcard, .eventon_list_event, "
    "article[class*='event'], li[class*='event']"
)
_FALLBACK_SEL = (
    "article, .event, [class*='event-card'], [class*='EventCard'], "
    "[class*='event-item'], [class*='EventItem']"
)


class WorldAffairsCouncilScraper(BaseScraper):
    SOURCE = "World Affairs Council of Charlotte"

    def scrape(self) -> list[dict]:
        events = self._scrape_via_api()
        if events:
            log.info("%s: found %d events (REST API)", self.SOURCE, len(events))
            return events

        log.debug("%s: API returned nothing, falling back to Playwright", self.SOURCE)
        events = self._scrape_via_playwright()
        log.info("%s: found %d events (Playwright)", self.SOURCE, len(events))
        return events

    # ------------------------------------------------------------------
    # Primary: Tribe Events Calendar REST API
    # ------------------------------------------------------------------
    def _scrape_via_api(self) -> list[dict]:
        events: list[dict] = []
        try:
            resp = requests.get(
                TRIBE_API,
                params={
                    "per_page": 25,
                    "start_date": date.today().isoformat(),
                },
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                    )
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.debug("%s Tribe API failed: %s", self.SOURCE, exc)
            return events

        for item in data.get("events", []):
            try:
                title = item.get("title", "").strip()
                if not title:
                    continue

                start_raw = item.get("start_date", "") or item.get("start_date_details", {})
                if isinstance(start_raw, dict):
                    start_raw = (
                        f"{start_raw.get('year')}-{start_raw.get('month', '01')}-"
                        f"{start_raw.get('day', '01')} "
                        f"{start_raw.get('hour', '00')}:{start_raw.get('minutes', '00')}"
                    )
                if not start_raw:
                    continue

                event_date = dateparser.parse(str(start_raw)).date()
                if not self._is_within_window(event_date):
                    continue

                venue_data = item.get("venue") or {}
                venue_str = venue_data.get("venue") or "World Affairs Council of Charlotte"
                desc = item.get("description", "") or ""
                # Strip HTML tags from description
                desc = re.sub(r"<[^>]+>", "", desc).strip()[:200]

                events.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(str(start_raw)),
                    "venue": venue_str,
                    "raw_description": desc,
                    "source": self.SOURCE,
                })
            except Exception as exc:
                log.debug("Event parse error: %s", exc)

        return events

    # ------------------------------------------------------------------
    # Fallback: Playwright CSS scraping of /current-events/
    # ------------------------------------------------------------------
    def _scrape_via_playwright(self) -> list[dict]:
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

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(1000)

                try:
                    page.wait_for_selector(_CARD_SEL, timeout=12000)
                except Exception:
                    pass

                cards = page.locator(_CARD_SEL).all()
                if not cards:
                    cards = page.locator(_FALLBACK_SEL).filter(
                        has=page.locator("time, [class*='date'], [class*='Date']")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        time_el = card.locator("time[datetime]").first
                        if time_el.count():
                            date_text = time_el.get_attribute("datetime") or ""
                        else:
                            date_el = card.locator(
                                "[class*='date'], [class*='Date'], "
                                ".tribe-event-date-start, .evcal_date"
                            ).first
                            date_text = (
                                date_el.inner_text().strip() if date_el.count() else ""
                            )

                        if not date_text:
                            continue

                        event_date = dateparser.parse(date_text, fuzzy=True).date()
                        if not self._is_within_window(event_date):
                            continue

                        title_el = card.locator(
                            "h2, h3, h4, [class*='title'], [class*='Title'], "
                            ".tribe-event-url, .evcal_event_title"
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
                log.error("%s Playwright scrape failed: %s", self.SOURCE, exc)
            finally:
                page.close()
                ctx.close()
                browser.close()

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
