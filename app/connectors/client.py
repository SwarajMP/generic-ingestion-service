"""The generic connector: given a SourceConfig + EndpointConfig, pulls every
page of records from a live HTTP API. This is the one piece of code that
talks to the network — everything source-specific lives in YAML, and
everything strategy-specific (how to authenticate, how to paginate) is
plugged in via the auth/pagination factories.
"""
import logging
import time
from typing import Iterator, Optional, Tuple

import httpx

from app.connectors.auth import build_auth_strategy
from app.connectors.extractor import extract_records
from app.connectors.pagination import build_pagination_strategy
from app.schemas import EndpointConfig, SourceConfig

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple fixed-interval limiter. Good enough for a single-worker demo;
    a shared/token-bucket limiter would be needed for concurrent workers
    hitting the same source (see README tradeoffs)."""

    def __init__(self, requests_per_second: float):
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._last_call = 0.0

    def wait(self):
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


class GenericApiConnector:
    """Pulls all pages of a single endpoint from a source, yielding
    (page_index, records) as it goes so the engine can persist incrementally
    instead of buffering an entire ingestion run in memory."""

    def __init__(self, source: SourceConfig, endpoint: EndpointConfig, http_client: Optional[httpx.Client] = None):
        self.source = source
        self.endpoint = endpoint
        self.auth = build_auth_strategy(source.auth)
        self.paginator = build_pagination_strategy(endpoint.pagination, endpoint.records_path)
        self.rate_limiter = RateLimiter(source.rate_limit.requests_per_second)
        self._client = http_client or httpx.Client(timeout=source.timeout_seconds)
        self._owns_client = http_client is None

    def close(self):
        if self._owns_client:
            self._client.close()

    def _full_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return self.source.base_url.rstrip("/") + "/" + path_or_url.lstrip("/")

    def _request_with_retry(self, method: str, url: str, params: dict, headers: dict) -> httpx.Response:
        max_attempts = max(1, self.source.retry.max_attempts)
        backoff = self.source.retry.backoff_factor
        attempt = 0
        while True:
            attempt += 1
            self.rate_limiter.wait()
            try:
                resp = self._client.request(method, url, params=params, headers=headers)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                retryable = status == 429 or (status is not None and status >= 500)
                if not retryable or attempt >= max_attempts:
                    logger.error("Request failed (status=%s) after %s attempt(s): %s", status, attempt, url)
                    raise
            except httpx.TransportError as exc:
                if attempt >= max_attempts:
                    logger.error("Request failed after %s attempt(s): %s (%s)", attempt, url, exc)
                    raise
            sleep_for = backoff * (2 ** (attempt - 1))
            logger.warning("Attempt %s/%s for %s failed; retrying in %.2fs", attempt, max_attempts, url, sleep_for)
            time.sleep(sleep_for)

    def fetch_all(self) -> Iterator[Tuple[int, list]]:
        base_params = dict(self.endpoint.params)
        params = self.paginator.initial_params(base_params)
        headers = dict(self.endpoint.headers)
        url = self._full_url(self.endpoint.path)
        page_index = 0

        while True:
            req_params, req_headers = self.auth.apply(params, headers)
            resp = self._request_with_retry(self.endpoint.method, url, req_params, req_headers)
            body = resp.json()
            records = extract_records(body, self.endpoint.records_path)
            yield page_index, records

            next_req = self.paginator.next_request(resp, params, page_index)
            if not next_req:
                break
            if "url" in next_req:
                url = next_req["url"]
                params = {}
            else:
                params = next_req.get("params", params)
            page_index += 1
