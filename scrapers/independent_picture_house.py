import logging
import re
from datetime import date, datetime

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# /upcoming-films/ lists films with release/screening dates;
# homepage may also have a now-playing section with .show elements.
UPCOMING_URL = "https://www.independentpicturehouse.org/upcoming-films/"
HOME_URL = "https://www.independentpicturehouse.org/"


class IndependentPictureHouseScraper(BaseScraper):
    SOURCE = "The Independent Picture House"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                # Try the upcoming-films page first
                page.goto(UPCOMING_URL, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                events = _parse_film_page(page, self._is_within_window)

                if not events:
                    # Fall back to homepage which may have a now-playing section
                    page.goto(HOME_URL, timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=20000)
                    events = _parse_film_page(page, self._is_within_window)

                if not events:
                    _log_snapshot(page, self.SOURCE)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                page.close()
                ctx.close()
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _parse_film_page(page, in_window) -> list[dict]:
    events: list[dict] = []

    # Selector priority: known IPH class names → generic film/show blocks
    SELECTORS = (
        # Original scraper class (BEM pattern used on IPH)
        ".show, "
        # Common WordPress/custom film listing patterns
        "article[class*='film'], article[class*='movie'], "
        ".film-item, .movie-item, .film-card, "
        # Tribe Events (if they use it for screenings)
        "article.tribe_events_cat, .tribe-events-calendar-list__event-article, "
        # Generic fallbacks
        "article, .entry"
    )

    cards = page.locator(SELECTORS).filter(
        has=page.locator("h2, h3, h4, [class*='title']")
    ).all()

    for card in cards:
        try:
            title_el = card.locator(
                ".show__title, [class*='title'], [class*='film-title'], h2, h3, h4"
            ).first
            date_el = card.locator(
                ".show__date, time[datetime], [class*='date'], [class*='Date']"
            ).first
            desc_el = card.locator(
                ".show__subtitle, .show__description, "
                "[class*='description'], [class*='subtitle'], p"
            ).first

            title_text = title_el.inner_text().strip() if title_el.count() else ""
            if not title_text:
                continue

            date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
            date_text = date_attr or (
                date_el.inner_text().strip() if date_el.count() else ""
            )

            if date_text:
                try:
                    parsed = dateparser.parse(date_text, fuzzy=True)
                    event_date = _infer_year(parsed)
                except Exception:
                    date_text = ""

            if not date_text:
                # No date on listing page — use a near-future placeholder so
                # the film still surfaces (cinema showtimes are on individual pages)
                event_date = date.today()

            if not in_window(event_date):
                continue

            desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

            events.append({
                "title": title_text[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": "See website for showtimes",
                "venue": "The Independent Picture House, 4237 Raleigh St, Charlotte NC",
                "raw_description": desc_text,
                "source": "The Independent Picture House",
            })
        except Exception as exc:
            log.debug("Film parse error: %s", exc)

    return events


def _log_snapshot(page, label: str) -> None:
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot (no films found): %s", label, text)
    except Exception:
        pass


def _infer_year(parsed: datetime) -> date:
    today = date.today()
    d = parsed.date().replace(year=today.year)
    if d < today:
        d = d.replace(year=today.year + 1)
    return d
