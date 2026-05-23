# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

MCP server that exposes the Organizze v2 REST API (`https://api.organizze.com.br/rest/v2`) as MCP tools, usable by any MCP client (Claude Desktop, etc.).

## Core architecture

The server is **generated entirely from an OpenAPI spec** — there is almost no hand-written tool code:

- `src/mcp_organizze/server.py` loads `src/mcp_organizze/openapi.yaml` and calls `FastMCP.from_openapi(...)`. Every MCP tool (e.g. `getTransactions`, `updateTransaction`) is derived from an `operationId` in that spec. To add, remove, or change a tool you edit `openapi.yaml`, **not** Python.
- The `httpx.AsyncClient` in `server.py` is the only HTTP layer: base URL, HTTP Basic auth (`ORGANIZZE_EMAIL` / `ORGANIZZE_API_KEY`), a custom `User-Agent`, and a response-logging event hook gated on `LOG_LEVEL=DEBUG` or `DEBUG_RESPONSE=true`.
- `src/mcp_organizze/__main__.py` is the entrypoint. Transports: `stdio` (default, for Claude Desktop) and `streamable-http` (`--host`/`--port`, default for Docker).

### FastMCP `allOf` gotcha (important)

FastMCP does **not** flatten `allOf` in a `requestBody` schema — body properties silently vanish from the generated tool, leaving only path/extra params. This was the root cause of broken partial-update PUTs. The fix pattern, already applied to `PUT /transactions/{id}` and `PUT /credit_cards/{id}`:

- Use a **dedicated update schema** (e.g. `TransactionUpdateInput`, `CreditCardUpdateInput`) with **no `required` block** so partial updates work, fold any extra PUT-only fields (`update_future`, `update_all`, `update_invoices_since`) into it, and reference it with a **direct `$ref`** — never `allOf`.
- The smoke test `test_no_request_body_uses_allof` enforces this across the whole spec; keep it green.

## Commands

```bash
# Run the server locally (stdio)
python -m mcp_organizze
python -m mcp_organizze --transport streamable-http --port 8000

# Run via uv without installing (dependencies resolved from pyproject.toml)
uv run python -m mcp_organizze

# Tests (smoke suite over the generated tools)
uv run --group dev pytest -q
uv run --group dev pytest tests/test_smoke.py::test_update_transaction_allows_partial_update -v   # single test
```

Required env vars (see `.env.example`; `python-dotenv` auto-loads a `.env`): `ORGANIZZE_EMAIL`, `ORGANIZZE_API_KEY`. Missing credentials only warn — tools still generate, which is why the test suite runs without them.

## Dependencies are declared in two places — keep them in sync

- `pyproject.toml` — source of truth for the package + the `dev` dependency group (pytest). `uv.lock` is committed.
- `requirements.txt` — used **only** by the `Dockerfile` (`pip install -r requirements.txt`). When you change runtime deps in `pyproject.toml`, mirror them here or the Docker image drifts.

## Publishing (CI)

- Push a `v*` tag → `publish.yml` builds and publishes to PyPI. Bump `version` in `pyproject.toml` before tagging.
- Push to `master` or a `v*` tag → `docker-publish.yml` builds and pushes the multi-arch image to Docker Hub (`samuelmoraesf/mcp-organizze`).