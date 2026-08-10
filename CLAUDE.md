# Chiwawa — AI Agent Registry

Public discovery platform for AI agents across A2A and MCP protocols. Deployed at https://chiwawa.vercel.app. Listed on the official MCP registry via `server.json`.

## What it does
- Crawls and indexes AI agents from Smithery and GitHub
- Exposes a public REST API for browsing/searching agents
- Exposes an MCP server so AI clients can search the registry directly
- Has a web dashboard for human browsing, with agent detail pages

## Stack
- **Backend API**: FastAPI (Python), deployed as Vercel serverless functions (`/api/index.py`)
- **MCP server**: Python, SSE endpoint at `/mcp/sse` (`/mcp/main.py`, `smithery.py`, `github_search.py`)
- **Crawler**: Python scripts that ingest from Smithery + GitHub (`/mcp/main.py`)
- **Dashboard**: `/dashboard` (frontend)
- **Database**: Neon Postgres (connection via `DATABASE_URL` in `.env`)
- **Deployment**: Vercel (`vercel.json`)

## Project phases (built over ~3 days starting Aug 6, 2026)
1. Core crawler + Postgres schema — ingesting agents from Smithery and GitHub
2. FastAPI REST API — `/agents`, `/stats`, `/agents/{id}` endpoints
3. MCP server — `search_agents` tool exposed over SSE
4. Dashboard — browse page, agent detail pages, copy URL button
5. Observability — IP + user-agent logging for API and MCP calls
6. MCP registry listing — `server.json` submitted to official registry

## Key files
- `api/index.py` — REST API (FastAPI), includes x402 payment middleware (disabled by default)
- `mcp/main.py` — MCP ingestion entry point
- `mcp/smithery.py` — Smithery crawler
- `mcp/github_search.py` — GitHub MCP repo search
- `migrations/` — DB migration scripts + query helpers
- `migrations/stats.py` — usage stats (API + MCP calls, totals, last 24h, by endpoint/tool)
- `db/` — schema definitions

## Running stats
```
python migrations/stats.py
```
Loads `DATABASE_URL` from `.env`. Shows total API calls, MCP calls, last 24h, recent entries with IP/UA.

## DB tables
- `api_calls` — columns: `called_at`, `endpoint`, `ip`, `user_agent`
- `mcp_calls` — columns: `called_at`, `tool_name`, `success`, `ip`, `user_agent`

## Usage as of Aug 10, 2026
- API: 23 total calls since Aug 8. Endpoints: `/agents` (11), `/stats` (9), `/agents/{id}` (3)
- MCP: 5 total calls (all `search_agents`, all successful). Last use Aug 8.
- Early calls (Aug 8) have no IP/UA — logging was added after those.
- Known external IPs: `23.23.253.54` (crawler), `23.27.145.161` (Mac browser)

## Environment
- `.env` — local secrets including `DATABASE_URL` (Neon Postgres)
- `.env.local` — Vercel OIDC token (pulled by Vercel CLI)
- `.env.production` — production env vars
