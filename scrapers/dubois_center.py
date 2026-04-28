import logging
import re
from datetime import date

import requests
from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Localist JSON API — returns upcoming events for the whole UNC Charlotte campus.
# We filter to Dubois Center by keyword; the API supports ?q= and ?days= parameters.
LOCALIST_API = "https://events.charlotte.edu/api/2/events"
LOCALIST_EVENTS_URL = "https://events.charlotte.edu/"


class DuboisCenterScraper(BaseScraper):
    SOURCE = "Dubois Center at UNC Charlotte"

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
    # Primary: Localist REST API
    # ------------------------------------------------------------------
    def _scrape_via_api(self) -> list[dict]:
        events: list[dict] = []
        today = date.today()

        try:
            resp = requests.get(
                LOCALIST_API,
                params={"days": self.DATE_WINDOW_DAYS, "pp": 100},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.debug("%s API fetch failed: %s", self.SOURCE, exc)
            return events

        for wrapper in data.get("events", []):
            item = wrapper.get("event", {})
            try:
                title = item.get("title", "").strip()
                if not title:
                    continue

                start_raw = item.get("starts_at") or item.get("first_date", "")
                if not start_raw:
                    continue

                event_date = dateparser.parse(start_raw).date()
                if not self._is_within_window(event_date):
                    continue

                time_str = _extract_time(start_raw)
                location = (
                    item.get("location_name") or item.get("location") or "UNC Charlotte"
                ).strip()
                desc = (item.get("description") or item.get("description_text") or "").strip()

                events.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": time_str,
                    "venue": f"{location}, UNC Charlotte",
                    "raw_description": desc[:200],
                    "source": self.SOURCE,
                })
            except Exception as exc:
                log.debug("Event parse error: %s", exc)

        return events

    # ------------------------------------------------------------------
    # Fallback: Playwright CSS scraping
    # ------------------------------------------------------------------
    def _scrape_via_playwright(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(LOCALIST_EVENTS_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.wait_for_timeout(3000)

                # Localist v4/v5 card selectors
                try:
                    page.wait_for_selector(
                        ".em-card, .lc-event-card, .event-card", timeout=10000
                    )
                except Exception:
                    pass

                cards = page.locator(".em-card, .lc-event-card, .event-card").all()
                if not cards:
                    cards = page.locator("article, li").filter(
                        has=page.locator("time[datetime]")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        title_el = card.locator(
                            "h3, h2, h4, "
                            ".em-card-title, .lc-event-card-title, [class*='title']"
                        ).first
                        date_el = card.locator(
                            "time[datetime], .em-date-badge, [class*='date']"
                        ).first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            continue

                        date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                        date_text = date_attr or (
                            date_el.inner_text().strip() if date_el.count() else ""
                        )
                        if not date_text:
                            continue

                        event_date = dateparser.parse(date_text.strip()).date()
                        if not self._is_within_window(event_date):
                            continue

                        desc_el = card.locator(
                            "p, .em-card-description, [class*='description']"
                        ).first
                        desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "UNC Charlotte / Dubois Center",
                            "raw_description": desc_text,
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
    # ISO 8601: "2026-04-28T18:00:00-04:00" → "06:00 PM"
    m = re.search(r"T(\d{2}):(\d{2})", text)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12:02d}:{mn} {suffix}"
    return "TBD"
