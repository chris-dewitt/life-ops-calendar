import logging
from datetime import date

import requests
from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper
from ._common import extract_jsonld_events, extract_time, log_snapshot

log = logging.getLogger(__name__)

# Davidson uses Localist (the dominant higher-ed events platform). Try API
# first; fall back to the public calendar HTML.
LOCALIST_API = "https://www.davidson.edu/calendar/api/2/events"
EVENTS_URL = "https://www.davidson.edu/events"
VENUE = "Davidson College, Davidson NC"

MAX_EVENTS = 12


class DavidsonCollegeScraper(BaseScraper):
    SOURCE = "Davidson College"

    def scrape(self) -> list[dict]:
        events = self._scrape_via_api()
        if events:
            log.info("%s: found %d events (API)", self.SOURCE, len(events))
            return self._cap(events)

        log.debug("%s: API empty, falling back to Playwright", self.SOURCE)
        events = self._scrape_via_playwright()
        log.info("%s: found %d events (Playwright)", self.SOURCE, len(events))
        return self._cap(events)

    def _cap(self, events: list[dict]) -> list[dict]:
        events.sort(key=lambda e: e["date"])
        return events[:MAX_EVENTS]

    def _scrape_via_api(self) -> list[dict]:
        events: list[dict] = []
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
                title = (item.get("title") or "").strip()
                start_raw = item.get("starts_at") or item.get("first_date", "")
                if not title or not start_raw:
                    continue

                event_date = dateparser.parse(start_raw).date()
                if not self._is_within_window(event_date):
                    continue

                location = (item.get("location_name") or item.get("location") or "Davidson College").strip()
                desc = (item.get("description") or item.get("description_text") or "").strip()

                events.append({
                    "title": title[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": extract_time(start_raw),
                    "venue": f"{location}, Davidson NC"[:80],
                    "raw_description": desc[:200],
                    "source": self.SOURCE,
                })
            except Exception as exc:
                log.debug("Event parse error: %s", exc)
        return events

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
                page.wait_for_timeout(2500)

                events = extract_jsonld_events(page, self.SOURCE, VENUE, self._is_within_window)
                if events:
                    return events

                # Localist v4/v5 cards + generic fallbacks
                selectors = (
                    ".em-card, .lc-event-card, .event-card, "
                    "article[class*='event'], li[class*='event']"
                )
                cards = page.locator(selectors).all()
                if not cards:
                    log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        title_el = card.locator(
                            "h2, h3, h4, .em-card-title, [class*='title']"
                        ).first
                        date_el = card.locator(
                            "time[datetime], .em-date-badge, [class*='date']"
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

        return events
