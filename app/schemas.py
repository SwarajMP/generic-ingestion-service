from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    type: Literal["none", "api_key_query", "api_key_header", "bearer", "basic"] = "none"
    param_name: Optional[str] = None       # api_key_query: query param name
    header_name: Optional[str] = None      # api_key_header: header name
    token_env: Optional[str] = None        # api_key_query/header/bearer: env var holding the secret
    username_env: Optional[str] = None     # basic
    password_env: Optional[str] = None     # basic


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 0.5  # seconds; exponential: backoff_factor * 2**(attempt-1)


class RateLimitConfig(BaseModel):
    requests_per_second: float = 5.0


class PaginationConfig(BaseModel):
    type: Literal["none", "page_number", "offset_limit", "next_url", "link_header"] = "none"
    page_param: str = "page"
    start_page: int = 1
    offset_param: str = "offset"
    limit_param: str = "limit"
    page_size: int = 50
    next_field: Optional[str] = None  # dotted-path to the next-page URL/cursor in the response body
    max_pages: int = 100               # safety cap so a misbehaving API can't loop forever


class EndpointConfig(BaseModel):
    name: str
    path: str
    method: str = "GET"
    params: Dict[str, Any] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    records_path: str = "$"          # dotted-path to the list of records; "$" means the response root
    id_field: Optional[str] = None   # dotted-path *within a record* used as its external id


class SourceConfig(BaseModel):
    name: str
    base_url: str
    auth: AuthConfig = Field(default_factory=AuthConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    timeout_seconds: float = 15.0
    endpoints: List[EndpointConfig]
