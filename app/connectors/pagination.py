"""Pagination strategies. Each implements two things:
  - initial_params(base_params): the query params for page 1
  - next_request(response, current_params, page_index): None to stop, or a
    dict with either {"url": <full next url>} or {"params": <next params>}
    to continue.

All four styles a REST API is likely to use are covered: no pagination,
page-number, offset/limit, a "next" link embedded in the body (PokeAPI),
and a "next" link in the HTTP Link header (GitHub). Adding a fifth style
(e.g. a cursor token in a response header) means adding one class here and
one entry to the factory below — nothing else in the app changes.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

from app.connectors.extractor import dotted_get, extract_records
from app.schemas import PaginationConfig


class PaginationStrategy(ABC):
    @abstractmethod
    def initial_params(self, base_params: Dict) -> Dict:
        ...

    @abstractmethod
    def next_request(self, response: httpx.Response, current_params: Dict, page_index: int) -> Optional[Dict[str, Any]]:
        ...


class NonePagination(PaginationStrategy):
    def initial_params(self, base_params):
        return dict(base_params)

    def next_request(self, response, current_params, page_index):
        return None


class PageNumberPagination(PaginationStrategy):
    def __init__(self, cfg: PaginationConfig, records_path: str):
        self.cfg = cfg
        self.records_path = records_path

    def initial_params(self, base_params):
        return {**base_params, self.cfg.page_param: self.cfg.start_page, self.cfg.limit_param: self.cfg.page_size}

    def next_request(self, response, current_params, page_index):
        if page_index + 1 >= self.cfg.max_pages:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        records = extract_records(body, self.records_path)
        if not records or len(records) < self.cfg.page_size:
            return None
        next_page = self.cfg.start_page + page_index + 1
        return {"params": {**current_params, self.cfg.page_param: next_page, self.cfg.limit_param: self.cfg.page_size}}


class OffsetLimitPagination(PaginationStrategy):
    def __init__(self, cfg: PaginationConfig, records_path: str):
        self.cfg = cfg
        self.records_path = records_path

    def initial_params(self, base_params):
        return {**base_params, self.cfg.offset_param: 0, self.cfg.limit_param: self.cfg.page_size}

    def next_request(self, response, current_params, page_index):
        if page_index + 1 >= self.cfg.max_pages:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        records = extract_records(body, self.records_path)
        if not records or len(records) < self.cfg.page_size:
            return None
        next_offset = (page_index + 1) * self.cfg.page_size
        return {"params": {**current_params, self.cfg.offset_param: next_offset, self.cfg.limit_param: self.cfg.page_size}}


class NextUrlPagination(PaginationStrategy):
    """E.g. PokeAPI: {"results": [...], "next": "https://.../?offset=20&limit=20"}"""

    def __init__(self, cfg: PaginationConfig):
        self.cfg = cfg

    def initial_params(self, base_params):
        return dict(base_params)

    def next_request(self, response, current_params, page_index):
        if page_index + 1 >= self.cfg.max_pages:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        next_url = dotted_get(body, self.cfg.next_field or "next")
        if not next_url:
            return None
        return {"url": next_url}


def parse_link_header(header_value: str, rel: str) -> Optional[str]:
    """Parse an RFC 5988 Link header (GitHub's pagination mechanism) and
    return the URL for the given rel, or None."""
    for part in header_value.split(","):
        segments = [s.strip() for s in part.split(";")]
        if len(segments) < 2:
            continue
        url_part = segments[0]
        if not (url_part.startswith("<") and url_part.endswith(">")):
            continue
        if f'rel="{rel}"' in segments[1:]:
            return url_part[1:-1]
    return None


class LinkHeaderPagination(PaginationStrategy):
    """E.g. GitHub: Link: <...?page=2>; rel="next", <...?page=9>; rel="last" """

    def __init__(self, cfg: PaginationConfig):
        self.cfg = cfg

    def initial_params(self, base_params):
        return dict(base_params)

    def next_request(self, response, current_params, page_index):
        if page_index + 1 >= self.cfg.max_pages:
            return None
        link_header = response.headers.get("link")
        if not link_header:
            return None
        next_url = parse_link_header(link_header, "next")
        if not next_url:
            return None
        return {"url": next_url}


def build_pagination_strategy(cfg: PaginationConfig, records_path: str) -> PaginationStrategy:
    if cfg.type == "none":
        return NonePagination()
    if cfg.type == "page_number":
        return PageNumberPagination(cfg, records_path)
    if cfg.type == "offset_limit":
        return OffsetLimitPagination(cfg, records_path)
    if cfg.type == "next_url":
        return NextUrlPagination(cfg)
    if cfg.type == "link_header":
        return LinkHeaderPagination(cfg)
    raise ValueError(f"Unsupported pagination type: {cfg.type}")
