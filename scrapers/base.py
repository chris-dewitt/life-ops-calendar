from abc import ABC, abstractmethod
from datetime import date, timedelta


class BaseScraper(ABC):
    DATE_WINDOW_DAYS = 30

    @abstractmethod
    def scrape(self) -> list[dict]:
        """Return list of raw event dicts with keys:
        title, date (YYYY-MM-DD), time (HH:MM AM/PM), venue, raw_description, source
        """
        ...

    def _is_within_window(self, event_date: date) -> bool:
        today = date.today()
        return today <= event_date <= today + timedelta(days=self.DATE_WINDOW_DAYS)

    def _playwright_context(self):
        from playwright.sync_api import sync_playwright
        return sync_playwright()
