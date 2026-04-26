import logging
import re
from datetime import date, datetime

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)
EVENTS_URL = "https://www.independentpicturehouse.org/"


class IndependentPictureHouseScraper(BaseScraper):
    SOURCE = "The Independent Picture House"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                for show in page.locator(".show").all():
                    try:
                        date_el = show.locator(".show__date").first
                        title_el = show.locator(".show__title, h2, h3").first
                        desc_el = show.locator(".show__subtitle, .show__description").first

                        date_text = date_el.inner_text().strip() if date_el.count() else ""
                        title_text = title_el.inner_text().strip() if title_el.count() else ""

                        if not title_text or not date_text:
                            continue

                        try:
                            parsed = dateparser.parse(date_text)
                            event_date = _infer_year(parsed)
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": "See website for showtimes",
                            "venue": "The Independent Picture House, 4237 Raleigh St, Charlotte NC",
                            "raw_description": desc_text,
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Show parse error: %s", exc)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _infer_year(parsed: datetime) -> date:
    today = date.today()
    d = parsed.date().replace(year=today.year)
    if d < today:
        d = d.replace(year=today.year + 1)
    return d
