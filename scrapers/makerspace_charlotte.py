import logging
import re
from datetime import date

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Primary: their own website; fallback: Eventbrite organizer page
PRIMARY_URL = "https://www.makerspacecharlotte.com/events"
FALLBACK_URL = "https://www.eventbrite.com/o/makerspace-charlotte-8173870117"


class MakerSpaceScraper(BaseScraper):
    SOURCE = "MakerSpace Charlotte"

    def scrape(self) -> list[dict]:
        events = _scrape_own_site(self._launch, self._new_context, self._is_within_window)
        if not events:
            log.debug("Own site yielded nothing, falling back to Eventbrite")
            events = _scrape_eventbrite(self._launch, self._new_context, self._is_within_window)
        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_own_site(launch_fn, new_ctx_fn, in_window) -> list[dict]:
    results = []
    with sync_playwright() as p:
        browser = launch_fn(p)
        ctx = new_ctx_fn(browser)
        page = ctx.new_page()
        try:
            page.goto(PRIMARY_URL, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            page.wait_for_timeout(3000)

            cards = page.locator(
                "article, .event, [class*='event-card'], "
                "[class*='EventCard'], li[class*='event']"
            ).filter(has=page.locator("time, [class*='date']")).all()

            for card in cards:
                try:
                    title_el = card.locator("h2, h3, h4, [class*='title']").first
                    date_el = card.locator("time, [class*='date']").first

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
                        "venue": "MakerSpace Charlotte, 1216 Thomas Ave, Charlotte NC",
                        "raw_description": "",
                        "source": "MakerSpace Charlotte",
                    })
                except Exception as exc:
                    log.debug("Own-site card error: %s", exc)
        except Exception as exc:
            log.debug("MakerSpace own-site scrape: %s", exc)
        finally:
            page.close()
            ctx.close()
            browser.close()
    return results


def _scrape_eventbrite(launch_fn, new_ctx_fn, in_window) -> list[dict]:
    results = []
    with sync_playwright() as p:
        browser = launch_fn(p)
        ctx = new_ctx_fn(browser)
        page = ctx.new_page()
        try:
            page.goto(FALLBACK_URL, timeout=30000)
            # Eventbrite is React-heavy — networkidle + extra delay
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            page.wait_for_timeout(5000)

            for card in page.locator(
                "[data-testid='event-card'], .eds-event-card, article[class*='event']"
            ).all():
                try:
                    title_el = card.locator(
                        "[data-testid='event-card-title'], h2, h3, [class*='title']"
                    ).first
                    date_el = card.locator(
                        "[data-testid='event-card-date'], time, [class*='date']"
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

                    if not in_window(event_date):
                        continue

                    results.append({
                        "title": title_text[:100],
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": _extract_time(date_text),
                        "venue": "MakerSpace Charlotte, 1216 Thomas Ave, Charlotte NC",
                        "raw_description": "",
                        "source": "MakerSpace Charlotte",
                    })
                except Exception as exc:
                    log.debug("Eventbrite card error: %s", exc)
        except Exception as exc:
            log.error("MakerSpace Eventbrite scrape failed: %s", exc)
        finally:
            page.close()
            ctx.close()
            browser.close()
    return results


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
