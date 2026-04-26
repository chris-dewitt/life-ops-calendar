from abc import ABC, abstractmethod
from datetime import date, timedelta

from playwright.sync_api import Browser, BrowserContext, Playwright

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


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

    def _new_context(self, browser: Browser) -> BrowserContext:
        """Create a browser context with anti-bot settings."""
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return ctx

    def _launch(self, p: Playwright) -> Browser:
        return p.chromium.launch(headless=True, args=BROWSER_ARGS)
