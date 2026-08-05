# Generic Data Ingestion Service

A service that ingests data from an arbitrary REST API and stores it, where
"arbitrary" is enforced by construction: **adding a new data source is a YAML
file, not a code change.** Demonstrated live against three structurally
different public APIs (different auth mechanisms and different pagination
styles) with zero source-specific code.

## Live hosted instance

**https://intentwise-ingestion-0z4w.onrender.com**

- Swagger UI: https://intentwise-ingestion-0z4w.onrender.com/docs
- `GET /sources` — configured sources
- `POST /ingest/{source}/{endpoint}` — trigger ingestion (e.g. `/ingest/pokeapi/pokemon`)
- `GET /runs` — ingestion run history

Hosted on Render's free tier, which spins the instance down after ~15 minutes
of inactivity — the first request after a period of idleness may take
30-50 seconds to wake it back up. Subsequent requests are fast.

## How to run it

### Option A: Docker Compose (recommended, single command)

```bash
docker compose up -d --build
```

This starts Postgres and the API on `http://localhost:8000`. Source configs
in `sources_config/*.yaml` are loaded automatically on startup — you'll see
`Loaded 3 source(s): ['github', 'jsonplaceholder', 'pokeapi']` in the logs.

Trigger an ingestion run:

```bash
curl -X POST http://localhost:8000/ingest/pokeapi/pokemon
curl -X POST http://localhost:8000/ingest/github/anthropic_repos
curl -X POST http://localhost:8000/ingest/jsonplaceholder/posts
```

Inspect what happened:

```bash
curl http://localhost:8000/sources          # what's configured
curl http://localhost:8000/runs             # ingestion run history (status, page/record counts, errors)
curl http://localhost:8000/runs/<run_id>    # one run's detail
```

Or look directly in Postgres (`localhost:5432`, user/pass/db = `ingestion`):

```sql
SELECT source_name, endpoint_name, count(*) FROM raw_records GROUP BY 1, 2;
```

To use an authenticated GitHub pull (5000 req/hr instead of 60/hr), set
`GITHUB_TOKEN` in a `.env` file before `docker compose up` — but it isn't
required, the demo above runs unauthenticated.

### Option B: Local Python (for running the test suite)

```bash
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
pytest tests/ -v
```

39 tests, no network and no database required — HTTP is mocked with `respx`
and the engine tests use an in-memory fake `Destination`/session so they
exercise the exact same orchestration code path the real app uses.

## The public APIs used

| Source | Auth | Pagination | Why it was picked |
|---|---|---|---|
| [PokeAPI](https://pokeapi.co) | none | `next` URL embedded in the response body | Simplest possible case; proves the baseline pipeline |
| [GitHub REST API](https://docs.github.com/en/rest) | optional Bearer token | `Link` HTTP header (RFC 5988, `rel="next"`) | Different auth (header token vs. none) *and* a completely different pagination transport (HTTP header vs. JSON body) |
| [JSONPlaceholder](https://jsonplaceholder.typicode.com) | none | none (single response) | Shows the "add a source = add a YAML file" claim with the simplest possible config |

Between them these exercise 3 of the 5 pagination strategies and 2 of the 4
auth strategies implemented (`page_number` and `offset_limit` pagination,
plus `api_key_query`/`api_key_header`/`basic` auth, are implemented and unit
tested but not exercised by a live demo source — see Tradeoffs).

## Architecture

```
sources_config/*.yaml  →  SourceConfig / EndpointConfig (pydantic)
                                   │
                     GenericApiConnector (app/connectors/client.py)
                        ├─ AuthStrategy        (app/connectors/auth.py)
                        ├─ PaginationStrategy  (app/connectors/pagination.py)
                        └─ extract_records/extract_id (app/connectors/extractor.py)
                                   │
                       IngestionEngine (app/ingestion/engine.py)
                                   │
                          Destination interface (app/destinations/base.py)
                                   ├─ PostgresDestination (implemented)
                                   └─ S3Destination (reference stub)
```

**Config-driven sources, not code-driven ones.** Each source is a YAML file
describing its base URL, auth mechanism, retry/rate-limit policy, and one or
more endpoints (path, static params, pagination style, and where in the
response the records/id live). `app/sources/loader.py` loads every file in
`sources_config/` at startup. There is no `if source == "pokeapi"` anywhere
in the codebase — the whole point of the exercise.

**Strategy pattern for the two axes that actually vary across real APIs:**
auth (`none` / `api_key_query` / `api_key_header` / `bearer` / `basic`) and
pagination (`none` / `page_number` / `offset_limit` / `next_url` /
`link_header`). Each is a small, independently unit-tested class behind a
factory function. Adding a sixth pagination style (say, a cursor in a
response header) means adding one class and one line to a factory — nothing
about the connector, engine, or API layer changes.

**A tiny dotted-path resolver instead of a JSONPath dependency.**
`records_path` and `id_field` in the config use `a.b.c` / `$` (root) /
`a.0` (list index) rather than full JSONPath. Every real response shape we
needed — a top-level array, a named list field, a nested field — is
expressible this way, and it's ~30 dependency-free lines
(`app/connectors/extractor.py`). If a source ever needs predicates or
wildcards, that file is the one seam to swap for `jsonpath-ng` without
touching any caller.

**Schema-less storage, keyed for idempotency.** `raw_records` stores the
untouched JSON payload in a `JSONB` column, keyed by
`(source_name, endpoint_name, external_id)`. This is what makes the *store*
generic too — the service never needs to know a source's shape ahead of
time to persist it. `external_id` comes from the configured `id_field`
when present; when a source has no natural key, it falls back to a SHA-256
hash of the canonical (sorted-key) JSON. Re-running an ingestion **upserts**
rather than duplicates, and a run that returns byte-identical data is a
no-op at the storage layer even with no natural key.

**Every run is recorded**, independent of the records it touched:
`ingestion_runs` tracks status, page count, record count, and the error
message on failure. `/runs` gives an operator visibility without grepping
logs, and it's the seam a future incremental/watermark strategy would hang
off (e.g. "since last successful run").

**`Destination` is an abstract interface**, not a concrete Postgres call
sprinkled through the engine. `app/destinations/s3_destination.py` is a
second implementation (untested live, no AWS creds in this environment) that
shows the shape: the engine and connector layer don't change at all to
write to object storage instead of — or in addition to — a database.

## Tradeoffs and assumptions

- **Full pull, capped by `max_pages`, every run.** There's no
  incremental/watermark sync (`?since=<last_run>`). For the demo sources
  that's fine (small, or naturally idempotent); for a real Amazon/Walmart
  volume you'd want a `since` param wired into the config and the last
  successful run's timestamp fed back in — noted below as the first thing
  I'd build next.
- **Single-process rate limiting.** `RateLimiter` is a per-connector
  fixed-interval sleep. It's correct for one worker hitting one source, but
  wouldn't coordinate across multiple concurrent workers or processes
  against the same source — that needs a shared limiter (Redis token
  bucket) once ingestion is horizontally scaled.
- **Retries cover transient failures (429 / 5xx / connection errors) with
  exponential backoff, not the full space of API failure modes.** No
  circuit breaker, no dead-letter queue for individual bad records within an
  otherwise-successful page, no partial-page recovery (a failed page fails
  the whole run past that point, though everything ingested before it is
  already committed since writes are per-page, not buffered for the whole
  run).
- **No auth flows that need a token exchange** (OAuth2 client-credentials /
  refresh tokens). The four strategies implemented cover static-credential
  auth, which is most public/partner APIs; a real Amazon Ads or Walmart
  Marketplace integration would need an `OAuth2ClientCredentialsAuth`
  strategy added alongside the existing four — same seam, not a redesign.
- **Records are stored as opaque JSON, not normalized into per-source
  tables.** This is deliberate — normalization is exactly the thing that
  makes ingestion source-specific again. The tradeoff is queryability: `SELECT * FROM raw_records WHERE payload->>'category' = 'x'` works today via
  JSONB operators, but anything needing joins or strong typing wants a
  transform step reading out of `raw_records` downstream, which is out of
  scope for "ingest and store."
- **Source configs are loaded once at startup**, not hot-reloaded or
  registrable via API. Adding a source today means adding a YAML file and
  restarting the container — a `POST /sources` endpoint that validates and
  registers a config at runtime would remove even that.
- **No hosted deployment.** I don't have a cloud account provisioned in
  this environment, so the submission runs via `docker compose up` rather
  than a public URL. Everything above was verified against Postgres and all
  three live APIs running exactly this way (see the AI-usage note below for
  what was actually executed, not just written).

## What I'd do with more time

1. **Incremental sync** — a `since_field`/watermark concept per endpoint, so
   a second run only pulls what changed instead of a full re-pull.
2. **Concurrency** — async httpx + a bounded worker pool so independent
   sources (and independent pages, where pagination allows out-of-order
   fetch) ingest in parallel instead of serially.
3. **Config-time validation against a live sample** — hit the endpoint once
   at registration time and sanity-check that `records_path`/`id_field`
   actually resolve, instead of only discovering a misconfiguration on
   first ingestion.
4. **A wired, tested S3Destination**, and the ability to fan out to more
   than one destination per run (write raw JSON to S3 *and* JSONB to
   Postgres) rather than swap one for the other.
5. **Alembic migrations** instead of `create_all` — fine for a take-home,
   not for a service anyone runs twice against evolving schemas.
6. **Structured JSON logs + basic metrics** (records/sec, error rate per
   source) — right now observability is `/runs` plus stdout logs.
7. **CI**: run the pytest suite plus a docker-compose-based smoke test
   (spin up Postgres, hit `/ingest/...`, assert row counts) on every push.

## AI usage note

This was built with Claude Code end-to-end — architecture, the auth/pagination
strategy implementations, the test suite, the Dockerfile/compose setup, and
this README. I directed the design decisions above (config-driven sources,
strategy pattern for auth/pagination, JSONB + hash-fallback for idempotency,
`Destination` as an abstract seam) and had Claude implement, test, and — critically —
actually *run* them: all 39 unit/integration tests were executed (not just
written), and the three live APIs were ingested through a real
`docker compose up` stack with Postgres, with the results (row counts, an
idempotent re-run, a 404 error path) inspected directly via `psql` and `curl`
rather than assumed from reading the code.

**Where it got something wrong, and how I caught it:** the first draft of
`GenericApiConnector.fetch_all()` applied the auth strategy once, before
entering the pagination loop, and reused the resulting params/headers for
every subsequent page. That's invisible for the two auth styles actually
used by header injection (bearer token) and no-auth, because headers persist
across the loop regardless. But tracing through what happens for
`api_key_query` auth combined with `next_url`/`link_header` pagination
exposed the bug: those styles follow a full URL handed back by the server
(GitHub's `Link` header, PokeAPI's `next` field) and, in this codebase, that
resets the request's query params to `{}` — silently dropping a query-string
API key from page 2 onward. Neither demo source exercises that specific
combination, so it wouldn't have surfaced in the two-API demo or by watching
the tests pass. I caught it by manually reasoning through the auth × pagination
interaction matrix rather than by a failing test, and fixed it by moving auth
application *inside* the pagination loop (`app/connectors/client.py`,
`fetch_all`), so it's freshly reapplied every page regardless of pagination
style. I added a unit test for the bearer+header case that *is* exercised
live, but I'm flagging here — rather than hiding — that the query-param-auth
path is verified only by `tests/test_auth.py` in isolation, not by an
end-to-end test through the connector. That gap is a fair thing to push on
in a follow-up round.
