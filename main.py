import logging
import sys

from pipeline.deduplicator import commit_ledger, filter_new
from pipeline.dispatcher import dispatch, send_error
from pipeline.filter import filter_interesting
from pipeline.minimizer import minimize
from scrapers import ALL_SCRAPERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    raw_events: list[dict] = []

    # Module A: scrape each source independently — one failure never stops the rest
    for ScraperClass in ALL_SCRAPERS:
        name = ScraperClass.__name__
        try:
            events = ScraperClass().scrape()
            log.info("%s returned %d event(s)", name, len(events))
            raw_events.extend(events)
        except Exception as exc:
            log.error("%s failed: %s", name, exc)

    log.info("Total raw events scraped: %d", len(raw_events))

    try:
        minimized = minimize(raw_events)
        new_events, new_hashes = filter_new(minimized)
        log.info("New events after deduplication: %d", len(new_events))

        if not new_events:
            log.info("No new events to dispatch.")
            return

        filtered = filter_interesting(new_events)
        log.info("After interest filter: %d/%d events kept", len(filtered), len(new_events))

        if filtered:
            log.info("Dispatching %d event(s) to MacroDroid...", len(filtered))
            dispatch(filtered)
        else:
            log.info("All events filtered out — nothing to dispatch.")

        # Commit ledger AFTER successful dispatch so failed runs are retried.
        # Includes filtered-out hashes so we don't re-evaluate them next run.
        commit_ledger(new_hashes)
        log.info("Ledger updated with %d new hashes.", len(new_hashes))

    except Exception as exc:
        msg = f"Pipeline failed: {exc}. Check GitHub logs."
        log.critical(msg)
        send_error(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
