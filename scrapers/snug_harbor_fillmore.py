import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

SNUG_URL = "https://www.snugharbor.com/events/"
FILLMORE_URL = "https://www.livenation.com/venue/KovZpZAEdFaA/the-fillmore-charlotte-events"


class SnugHarborFillmoreScraper(BaseScraper):
    SOURCE = "Snug Harbor & The Fillmore"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            events.extend(_scrape_snug(browser, self._new_context, self._is_within_window))
            events.extend(_scrape_fillmore(browser, self._new_context, self._is_within_window))
            browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_snug(browser, new_ctx, in_window) -> list[dict]:
    results = []
    ctx = new_ctx(browser)
    page = ctx.new_page()
    try:
        page.goto(SNUG_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        for card in page.locator(
            "article, .event, [class*='event-card'], [class*='EventCard'], "
            "li[class*='event'], .tribe-event"
        ).all():
            try:
                title_el = card.locator("h2, h3, h4, [class*='title'], [class*='name']").first
                date_el = card.locator("time, [class*='date'], [datetime]").first

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

                if not in_window(event_date):
                    continue

                results.append({
                    "title": title_text[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(date_text),
                    "venue": "Snug Harbor, 1228 Gordon St, Charlotte NC",
                    "raw_description": "",
                    "source": "Snug Harbor",
                })
            except Exception as exc:
                log.debug("Snug Harbor card error: %s", exc)

    except Exception as exc:
        log.error("Snug Harbor scrape failed: %s", exc)
    finally:
        page.close()
        ctx.close()

    return results


def _scrape_fillmore(browser, new_ctx, in_window) -> list[dict]:
    results = []
    ctx = new_ctx(browser)
    page = ctx.new_page()
    try:
        page.goto(FILLMORE_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        page.wait_for_timeout(4000)

        for card in page.locator(
            "[class*='event-card'], [class*='EventCard'], article[class*='event'], "
            "[data-testid*='event'], .event-listing-item"
        ).all():
            try:
                title_el = card.locator("h2, h3, [class*='title'], [class*='name']").first
                date_el = card.locator("time, [class*='date'], [datetime]").first

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

                if not in_window(event_date):
                    continue

                results.append({
                    "title": title_text[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(date_text),
                    "venue": "The Fillmore Charlotte, 820 Hamilton St, Charlotte NC",
                    "raw_description": "",
                    "source": "The Fillmore Charlotte",
                })
            except Exception as exc:
                log.debug("Fillmore card error: %s", exc)

    except Exception as exc:
        log.error("Fillmore scrape failed: %s", exc)
    finally:
        page.close()
        ctx.close()

    return results


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
