import httpx

from app.connectors.pagination import build_pagination_strategy, parse_link_header
from app.schemas import PaginationConfig


def test_none_pagination_never_continues():
    strategy = build_pagination_strategy(PaginationConfig(type="none"), "$")
    resp = httpx.Response(200, json=[{"id": 1}])
    assert strategy.next_request(resp, {}, 0) is None


def test_next_url_pagination_follows_body_field():
    cfg = PaginationConfig(type="next_url", next_field="next", max_pages=5)
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": 1}], "next": "https://api.example.com/page2"})
    assert strategy.next_request(resp, {}, 0) == {"url": "https://api.example.com/page2"}


def test_next_url_pagination_stops_when_next_is_null():
    cfg = PaginationConfig(type="next_url", next_field="next")
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [], "next": None})
    assert strategy.next_request(resp, {}, 0) is None


def test_next_url_pagination_respects_max_pages():
    cfg = PaginationConfig(type="next_url", next_field="next", max_pages=1)
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": 1}], "next": "https://x/page2"})
    assert strategy.next_request(resp, {}, 0) is None


def test_parse_link_header_finds_next():
    header = '<https://api.github.com/orgs/x/repos?page=2>; rel="next", <https://api.github.com/orgs/x/repos?page=5>; rel="last"'
    assert parse_link_header(header, "next") == "https://api.github.com/orgs/x/repos?page=2"


def test_parse_link_header_missing_rel_returns_none():
    header = '<https://api.github.com/orgs/x/repos?page=5>; rel="last"'
    assert parse_link_header(header, "next") is None


def test_link_header_pagination_follows_next_rel():
    cfg = PaginationConfig(type="link_header", max_pages=5)
    strategy = build_pagination_strategy(cfg, "$")
    resp = httpx.Response(200, json=[], headers={"link": '<https://x/repos?page=2>; rel="next"'})
    assert strategy.next_request(resp, {}, 0) == {"url": "https://x/repos?page=2"}


def test_link_header_pagination_stops_without_header():
    cfg = PaginationConfig(type="link_header")
    strategy = build_pagination_strategy(cfg, "$")
    resp = httpx.Response(200, json=[])
    assert strategy.next_request(resp, {}, 0) is None


def test_page_number_pagination_stops_on_short_page():
    cfg = PaginationConfig(type="page_number", page_size=10, max_pages=10)
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": i} for i in range(5)]})
    assert strategy.next_request(resp, {}, 0) is None


def test_page_number_pagination_continues_on_full_page():
    cfg = PaginationConfig(type="page_number", page_size=10, max_pages=10, page_param="page", start_page=1)
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": i} for i in range(10)]})
    result = strategy.next_request(resp, {"page": 1}, 0)
    assert result == {"params": {"page": 2, "limit": 10}}


def test_offset_limit_pagination_advances_offset():
    cfg = PaginationConfig(type="offset_limit", page_size=10, max_pages=10, offset_param="offset")
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": i} for i in range(10)]})
    result = strategy.next_request(resp, {"offset": 0}, 0)
    assert result == {"params": {"offset": 10, "limit": 10}}


def test_offset_limit_pagination_stops_on_short_page():
    cfg = PaginationConfig(type="offset_limit", page_size=10, max_pages=10)
    strategy = build_pagination_strategy(cfg, "results")
    resp = httpx.Response(200, json={"results": [{"id": 1}]})
    assert strategy.next_request(resp, {"offset": 0}, 0) is None
