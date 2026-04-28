import logging
import re

import requests
from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Eventbrite organizer profile — primary page approach
EVENTBRITE_URL = "https://www.eventbrite.com/o/makerspace-charlotte-8173870117"

# Eventbrite public search API — returns JSON, no auth required.
# Searching by organizer ID via the discovery endpoint.
EVENTBRITE_SEARCH_API = "https://www.eventbriteapi.com/v3/organizers/8173870117/events/"


class MakerSpaceScraper(BaseScraper):
    SOURCE = "MakerSpace Charlotte"

    def scrape(self) -> list[dict]:
        events = self._scrape_via_api()
        if events:
            log.info("%s: found %d events (API)", self.SOURCE, len(events))
            return events

        log.debug("%s: API returned nothing, falling back to Playwright", self.SOURCE)
        events = self._scrape_via_playwright()
        log.info("%s: found %d events (Playwright)", self.SOURCE, len(events))
        return events

    # ------------------------------------------------------------------
    # Primary: Eventbrite public organizer events API (no API key needed
    # for public event listings when using the /organizers/ endpoint)
    # ------------------------------------------------------------------
    def _scrape_via_api(self) -> list[dict]:
        events: list[dict] = []
        try:
            resp = requests.get(
                EVENTBRITE_SEARCH_API,
                params={"status": "live", "order_by": "start_asc", "expand": "venue"},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.eventbrite.com/",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.debug("%s API request failed: %s", self.SOURCE, exc)
            return events

        for item in data.get("events", []):
            try:
                title = item.get("name", {}).get("text", "").strip()
                if not title:
                    continue

                start = item.get("start", {}).get("local", "") or item.get("start", {}).get("utc", "")
                if not start:
                    continue

                event_date = dateparser.parse(start).date()
                if not self._is_within_window(event_date):
                    continue

                venue_data = item.get("venue") or {}
                address = venue_data.get("address", {})
                venue_str = (
                    venue_data.get("name")
                    or address.get("localized_address_display")
                    or "MakerSpace Charlotte, 1216 Thomas Ave, Charlotte NC"
                )

                events.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(start),
                    "venue": venue_str,
                    "raw_description": (item.get("description") or {}).get("text", "")[:200],
                    "source": self.SOURCE,
                })
            except Exception as exc:
                log.debug("Event parse error: %s", exc)

        return events

    # ------------------------------------------------------------------
    # Fallback: Playwright scraping of the organizer page
    # ------------------------------------------------------------------
    def _scrape_via_playwright(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTBRITE_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                # Scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(5000)

                # Eventbrite React testids — these change; try several variants
                CARD_SEL = (
                    "[data-testid='event-card'], "
                    "[data-testid='organizer-profile__event-card'], "
                    "[data-event-id], "
                    ".eds-event-card, article[class*='event']"
                )
                cards = page.locator(CARD_SEL).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        title_el = card.locator(
                            "[data-testid='event-card-title'], "
                            "[data-testid='event-title'], "
                            "h2, h3, [class*='title']"
                        ).first
                        date_el = card.locator(
                            "[data-testid='event-card-date'], "
                            "[data-testid='event-date'], "
                            "time, [class*='date']"
                        ).first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            continue

                        date_attr = (
                            date_el.get_attribute("datetime") if date_el.count() else ""
                        )
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
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "MakerSpace Charlotte, 1216 Thomas Ave, Charlotte NC",
                            "raw_description": "",
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Card error: %s", exc)

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
