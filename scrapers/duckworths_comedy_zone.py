import json
import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

COMEDY_ZONE_URL = "https://thecomedyzone.com/charlotte-nc/"


class DuckworthsComedyZoneScraper(BaseScraper):
    SOURCE = "The Comedy Zone"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(COMEDY_ZONE_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.wait_for_timeout(3000)

                # 1. JSON-LD (Yoast SEO / schema markup present on many WP sites)
                events = _extract_jsonld(page, self._is_within_window)
                if events:
                    log.info("%s: found %d events (JSON-LD)", self.SOURCE, len(events))
                    return events

                # 2. CSS selectors: try Comedy Zone's known class patterns and
                #    generic Lasso CRM / custom show-list patterns
                selectors = (
                    ".show-item, .show-row, .lasso-loop-item, "
                    ".shows-list li, .schedule-item, "
                    ".show, .event, article, [class*='show-card'], "
                    "[class*='event-card'], [class*='ShowCard']"
                )
                cards = page.locator(selectors).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)
                else:
                    for card in cards:
                        try:
                            title_el = card.locator(
                                "h2, h3, h4, "
                                "[class*='title'], [class*='name'], "
                                "[class*='performer'], [class*='headliner']"
                            ).first
                            date_el = card.locator(
                                "time, [class*='date'], [class*='Date'], [datetime]"
                            ).first

                            title_text = title_el.inner_text().strip() if title_el.count() else ""
                            if not title_text:
                                continue

                            date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                            date_text = date_attr or (date_el.inner_text().strip() if date_el.count() else "")
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
                                "time": _extract_time(card.inner_text()),
                                "venue": "Comedy Zone Charlotte, 900 NC Music Factory Blvd, Charlotte NC",
                                "raw_description": "",
                                "source": self.SOURCE,
                            })
                        except Exception as exc:
                            log.debug("Comedy Zone card error: %s", exc)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                page.close()
                ctx.close()
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _extract_jsonld(page, in_window) -> list[dict]:
    results = []
    for script in page.locator('script[type="application/ld+json"]').all():
        try:
            data = json.loads(script.inner_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                for entry in (item.get("@graph", []) or [item]):
                    if entry.get("@type", "") not in (
                        "Event", "MusicEvent", "ComedyEvent",
                        "TheaterEvent", "SocialEvent",
                    ):
                        continue
                    name = entry.get("name", "").strip()
                    start = entry.get("startDate", "")
                    if not name or not start:
                        continue
                    try:
                        event_date = dateparser.parse(start).date()
                    except Exception:
                        continue
                    if not in_window(event_date):
                        continue
                    results.append({
                        "title": name[:100],
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": _extract_time(start),
                        "venue": "Comedy Zone Charlotte, 900 NC Music Factory Blvd, Charlotte NC",
                        "raw_description": entry.get("description", "")[:200],
                        "source": "The Comedy Zone",
                    })
        except Exception:
            pass
    return results


def _log_snapshot(page, label: str) -> None:
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot (no cards found): %s", label, text)
    except Exception:
        pass


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
