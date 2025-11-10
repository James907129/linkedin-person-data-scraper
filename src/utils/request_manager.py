from __future__ import annotations

import time
from typing import Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class HttpError(Exception):
    pass

class RequestManager:
    def __init__(
        self,
        timeout: int = 20,
        default_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        backoff_base: float = 1.5,
        logger=None,
    ):
        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.log = logger

        # Respectful defaults
        if "User-Agent" not in self.default_headers:
            self.default_headers["User-Agent"] = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )

        self.session = requests.Session()
        self.session.headers.update(self.default_headers)

    def _log_debug(self, msg: str):
        if self.log:
            self.log.debug(msg)

    def _log_info(self, msg: str):
        if self.log:
            self.log.info(msg)

    def _log_warn(self, msg: str):
        if self.log:
            self.log.warning(msg)

    def _raise_for_status(self, resp: requests.Response):
        if resp.status_code >= 400:
            raise HttpError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.0, min=1, max=10),
        retry=retry_if_exception_type((requests.RequestException, HttpError)),
    )
    def _get_once(self, url: str) -> str:
        self._log_debug(f"GET {url}")
        resp = self.session.get(url, timeout=self.timeout)
        self._raise_for_status(resp)
        # Simple content-type guard
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            self._log_warn(f"Unexpected content type for {url}: {ctype}")
        return resp.text

    def get(self, url: str) -> str:
        html = self._get_once(url)
        # Polite short pause to be respectful to servers; explicit throttling handled in caller
        time.sleep(0.25)
        return html