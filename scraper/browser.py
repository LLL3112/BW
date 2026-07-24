"""Playwright-backed page fetcher.

halooglasi.com sits behind Cloudflare bot-protection that frequently issues a
JS challenge; a plain requests/cloudscraper session has historically come
back empty from CI runners (see data/*.csv history in this repo — every past
run produced a header-only file). A real headless browser executes the
challenge JS like a normal visitor would.

A real run from a residential/office IP (not a datacenter IP) still got
blocked partway through — the first several requests succeeded and returned
real listings, then everything started coming back HTTP 403. That points to
rate-limiting on request volume/speed rather than a static IP block, which is
why callers (scraper/run.py) pace requests with deliberate delays and trip a
circuit breaker on repeated consecutive failures instead of retrying forever.
"""
import logging
import time

from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from . import config

log = logging.getLogger("bw_scraper.browser")


class BrowserFetcher:
    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            user_agent=config.HEADERS["User-Agent"],
            locale="sr-RS",
            viewport={"width": 1366, "height": 900},
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.context.close()
            self.browser.close()
        finally:
            self._pw.stop()

    def get_html(self, url, *, wait_selector=None, max_retries=2, settle_ms=1500):
        # Only 2 attempts (not 3): once a block/rate-limit is active, extra
        # retries per URL just add more flagged requests without helping —
        # better to let the caller's rate-limit guard see the failure sooner.
        last_exc = None
        for attempt in range(1, max_retries + 1):
            page = self.context.new_page()
            try:
                resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
                status = resp.status if resp else None
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=9000)
                    except PWTimeoutError:
                        pass
                page.wait_for_timeout(settle_ms)
                html = page.content()
                page.close()
                if status and status >= 400:
                    log.warning("GET %s -> HTTP %s (attempt %d/%d)", url, status, attempt, max_retries)
                    time.sleep(8 * attempt)
                    continue
                return html, status
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("GET %s failed (attempt %d/%d): %s", url, attempt, max_retries, exc)
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(4 * attempt)
        if last_exc:
            raise last_exc
        return "", None
