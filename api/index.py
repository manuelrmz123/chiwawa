import json
import os
import re
import base64
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
load_dotenv()

app = FastAPI(
    title="Chiwawa API",
    description="Public registry of AI agents discovered automatically across A2A and MCP protocols.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# x402 — machine-native payments (switch off by default)
# ---------------------------------------------------------------------------

PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"
WALLET           = os.getenv("WALLET_ADDRESS", "0xF0Ea667ce6988a46Ff312ecbAe6d9447E59158f4")
USDC_BASE        = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
FACILITATOR_URL  = os.getenv("X402_FACILITATOR", "https://x402.org/api/v1/verify")

PRICE_LISTING = 1000   # $0.001 in USDC micro-units
PRICE_DETAIL  = 3000   # $0.003
FREE_LIMIT    = 3

_used_nonces: set = set()


def _requirements(price: int, resource: str, description: str) -> dict:
    return {
        "scheme": "exact",
        "network": "base-mainnet",
        "maxAmountRequired": str(price),
        "resource": resource,
        "description": description,
        "mimeType": "application/json",
        "payTo": WALLET,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USDC", "version": "2"},
    }


def payment_required(price: int, resource: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "x402Version": 1,
            "error": "Payment required",
            "free_tier": f"Call /agents without X-Payment to receive {FREE_LIMIT} results for free.",
            "accepts": [_requirements(price, resource, description)],
        },
    )


def verify_payment(header: str, price: int, resource: str, description: str) -> bool:
    try:
        import httpx
        resp = httpx.post(
            FACILITATOR_URL,
            json={"payment": header, "paymentRequirements": _requirements(price, resource, description)},
            timeout=10,
        )
        data = resp.json()
        if not data.get("isValid", False):
            return False
        try:
            payload = json.loads(base64.b64decode(header + "=="))
            nonce = payload.get("payload", {}).get("authorization", {}).get("nonce")
            if nonce:
                if nonce in _used_nonces:
                    return False
                _used_nonces.add(nonce)
        except Exception:
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn():
    url = os.getenv("DATABASE_URL", "").strip().lstrip('﻿￾')
    return psycopg2.connect(url)


def query(sql: str, params=None) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def jsn(data):
    return JSONResponse(content=json.loads(json.dumps(data, default=str)))


DOMAIN_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$')


# ---------------------------------------------------------------------------
# REST API routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    row = query("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'active') AS active FROM agents")[0]
    return jsn({
        "name": "Chiwawa",
        "description": "Unified public registry of AI agents across A2A and MCP protocols.",
        "version": "0.1.0",
        "agents": row["total"],
        "active_agents": row["active"],
        "docs": "/docs",
        "mcp": "/mcp/sse",
        "payments_enabled": PAYMENTS_ENABLED,
        "free_tier": {"agents_per_request": FREE_LIMIT},
        "pricing": {"listing": "$0.001 per request", "detail": "$0.003 per request"},
    })


@app.get("/stats")
def stats():
    totals = query("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE type = 'a2a') AS a2a,
               COUNT(*) FILTER (WHERE type = 'mcp_live') AS mcp_live,
               COUNT(*) FILTER (WHERE type = 'mcp_package') AS mcp_package
        FROM agents
    """)[0]
    by_status = query("SELECT status, COUNT(*) AS count FROM agents GROUP BY status ORDER BY count DESC")
    recent = query("""
        SELECT id::text, name, type, status, base_url, provider_name,
               first_seen_at AT TIME ZONE 'UTC' AS first_seen_at
        FROM agents ORDER BY first_seen_at DESC LIMIT 10
    """)
    crawls = query("""
        SELECT domain, checked_at AT TIME ZONE 'UTC' AS checked_at,
               http_status, response_time_ms, success, error_message
        FROM crawl_log ORDER BY checked_at DESC LIMIT 20
    """)
    seeds = query("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE next_crawl_at IS NULL) AS pending
        FROM seed_domains
    """)[0]
    return jsn({"totals": totals, "by_status": by_status, "recent_agents": recent,
                "recent_crawls": crawls, "seed_stats": seeds})


@app.get("/agents")
def list_agents(
    request: Request,
    type: str = Query(None, description="Filter by type: a2a, mcp_live, mcp_package"),
    status: str = Query(None, description="Filter by status: active, degraded, unresponsive, unreachable, gone, archived"),
    search: str = Query(None, description="Search by name or description"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    is_free_tier = False
    if PAYMENTS_ENABLED:
        payment_header = request.headers.get("X-Payment")
        if payment_header:
            if not verify_payment(payment_header, PRICE_LISTING, "/agents", "Agent listing"):
                return JSONResponse(status_code=402, content={"error": "Invalid or expired payment"})
        else:
            limit, page, is_free_tier = FREE_LIMIT, 1, True

    conditions, params = [], []
    if type:   conditions.append("type = %s");   params.append(type)
    if status: conditions.append("status = %s"); params.append(status)
    if search:
        conditions.append("(name ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]

    where  = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * limit
    total  = query(f"SELECT COUNT(*) AS n FROM agents {where}", params)[0]["n"]
    agents = query(f"""
        SELECT id::text, type, name, description, base_url, provider_name,
               status, version, consecutive_fails, dns_resolves, ssl_valid,
               last_http_status, last_seen_at, last_checked_at, first_seen_at
        FROM agents {where} ORDER BY first_seen_at DESC LIMIT %s OFFSET %s
    """, params + [limit, offset])

    return jsn({"total": total, "page": page, "limit": limit,
                "pages": max(1, (total + limit - 1) // limit),
                "agents": agents, "free_tier": is_free_tier})


@app.get("/agents/{agent_id}")
def get_agent(request: Request, agent_id: str):
    if PAYMENTS_ENABLED:
        ph = request.headers.get("X-Payment")
        if not ph:
            return payment_required(PRICE_DETAIL, f"/agents/{agent_id}", "Full agent detail")
        if not verify_payment(ph, PRICE_DETAIL, f"/agents/{agent_id}", "Agent detail"):
            return JSONResponse(status_code=402, content={"error": "Invalid or expired payment"})

    agents = query("""
        SELECT id::text, type, name, description, base_url, card_url,
               provider_name, provider_url, version, status, consecutive_fails,
               dns_resolves, ssl_valid, last_http_status, last_response_time_ms,
               last_seen_at, last_checked_at, last_status_change_at, first_seen_at,
               raw_card, card_hash
        FROM agents WHERE id = %s::uuid
    """, [agent_id])
    if not agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = agents[0]
    agent["skills"] = query(
        "SELECT skill_id, name, description, tags, examples FROM agent_skills WHERE agent_id = %s::uuid", [agent_id])
    agent["auth_schemes"] = [r["scheme"] for r in query(
        "SELECT scheme FROM agent_auth_schemes WHERE agent_id = %s::uuid", [agent_id])]
    agent["io_modes"] = query(
        "SELECT direction, mime_type FROM agent_io_modes WHERE agent_id = %s::uuid", [agent_id])
    return jsn(agent)


@app.get("/agents/{agent_id}/history")
def get_history(request: Request, agent_id: str):
    if PAYMENTS_ENABLED:
        ph = request.headers.get("X-Payment")
        if not ph:
            return payment_required(PRICE_DETAIL, f"/agents/{agent_id}/history", "Agent card history")
        if not verify_payment(ph, PRICE_DETAIL, f"/agents/{agent_id}/history", "Agent history"):
            return JSONResponse(status_code=402, content={"error": "Invalid or expired payment"})

    rows = query("""
        SELECT id::text, changed_at, previous_hash, new_hash, previous_card, new_card
        FROM agent_card_history WHERE agent_id = %s::uuid ORDER BY changed_at DESC
    """, [agent_id])
    return jsn(rows)


@app.get("/agents/{agent_id}/crawl_log")
def get_crawl_log(request: Request, agent_id: str):
    if PAYMENTS_ENABLED:
        ph = request.headers.get("X-Payment")
        if not ph:
            return payment_required(PRICE_DETAIL, f"/agents/{agent_id}/crawl_log", "Agent crawl log")
        if not verify_payment(ph, PRICE_DETAIL, f"/agents/{agent_id}/crawl_log", "Agent crawl log"):
            return JSONResponse(status_code=402, content={"error": "Invalid or expired payment"})

    rows = query("""
        SELECT id::text, domain, checked_at, http_status, response_time_ms, success, error_message
        FROM crawl_log WHERE agent_id = %s::uuid ORDER BY checked_at DESC LIMIT 20
    """, [agent_id])
    return jsn(rows)


_submissions: dict[str, list] = defaultdict(list)


@app.post("/submissions", status_code=201)
def submit_domain(request: Request, body: dict):
    domain = body.get("domain", "").strip().lower()
    if not domain or not DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="Invalid domain name")

    ip  = request.client.host
    now = datetime.now(timezone.utc)
    _submissions[ip] = [t for t in _submissions[ip] if now - t < timedelta(hours=1)]
    if len(_submissions[ip]) >= 5:
        raise HTTPException(status_code=429, detail="Rate limit: max 5 submissions per hour")
    _submissions[ip].append(now)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO seed_domains (domain, source, status) VALUES (%s, 'submission', 'pending') ON CONFLICT (domain) DO NOTHING",
            (domain,)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=409, detail="Domain already in registry")
        conn.commit()
    finally:
        conn.close()

    return {"domain": domain, "status": "queued", "message": "Domain added to crawl queue."}


# ---------------------------------------------------------------------------
# MCP Server — Phase 7
# Agents and Claude can query Chiwawa natively via the MCP protocol.
# SSE endpoint: GET /mcp/sse  |  Messages: POST /mcp/messages/
# ---------------------------------------------------------------------------

from mcp.server.fastmcp import FastMCP

_mcp = FastMCP(
    "chiwawa-registry",
    instructions=(
        "Chiwawa is a public registry of AI agents discovered automatically "
        "across A2A and MCP protocols. Use get_stats for an overview, "
        "search_agents to find agents, and get_agent for full details."
    ),
)


@_mcp.tool()
def get_stats() -> str:
    """
    Returns aggregate statistics for the Chiwawa AI agent registry:
    total agents indexed, breakdown by type (A2A, MCP Live, MCP Package),
    and breakdown by health status (active, degraded, unresponsive, etc.).
    """
    totals = query("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE type = 'a2a')         AS a2a,
               COUNT(*) FILTER (WHERE type = 'mcp_live')    AS mcp_live,
               COUNT(*) FILTER (WHERE type = 'mcp_package') AS mcp_package
        FROM agents
    """)[0]
    by_status = query(
        "SELECT status, COUNT(*) AS count FROM agents GROUP BY status ORDER BY count DESC"
    )
    return json.dumps({"totals": totals, "by_status": by_status}, default=str)


@_mcp.tool()
def search_agents(q: str = "", agent_type: str = "", status: str = "", limit: int = 10) -> str:
    """
    Search for AI agents in the Chiwawa registry.

    Args:
        q: Full-text search on name and description (case-insensitive).
        agent_type: Filter by type — one of: a2a, mcp_live, mcp_package.
        status: Filter by health status — one of: active, degraded, unresponsive, unreachable, gone, archived.
        limit: Number of results to return (1–20, default 10).
    """
    limit = min(int(limit), 20)
    conds, params = [], []
    if agent_type: conds.append("type = %s");   params.append(agent_type)
    if status:     conds.append("status = %s"); params.append(status)
    if q:
        conds.append("(name ILIKE %s OR description ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    where  = ("WHERE " + " AND ".join(conds)) if conds else ""
    agents = query(f"""
        SELECT id::text, name, type, status, base_url, description,
               first_seen_at AT TIME ZONE 'UTC' AS first_seen_at
        FROM agents {where} ORDER BY first_seen_at DESC LIMIT %s
    """, params + [limit])
    return json.dumps({"count": len(agents), "agents": agents}, default=str)


@_mcp.tool()
def get_agent(agent_id: str) -> str:
    """
    Get full details for a specific agent by its UUID.
    Returns provider, version, skills, auth schemes, and last 5 crawl results.

    Args:
        agent_id: The UUID of the agent (obtain IDs from search_agents results).
    """
    rows = query("""
        SELECT id::text, type, name, description, base_url, provider_name, version,
               status, consecutive_fails, dns_resolves, ssl_valid,
               first_seen_at AT TIME ZONE 'UTC' AS first_seen_at,
               last_seen_at  AT TIME ZONE 'UTC' AS last_seen_at
        FROM agents WHERE id = %s::uuid
    """, [agent_id])
    if not rows:
        return json.dumps({"error": "Agent not found"})
    agent = rows[0]
    agent["skills"] = query(
        "SELECT skill_id, name, description FROM agent_skills WHERE agent_id = %s::uuid",
        [agent_id],
    )
    agent["auth_schemes"] = [r["scheme"] for r in query(
        "SELECT scheme FROM agent_auth_schemes WHERE agent_id = %s::uuid", [agent_id]
    )]
    agent["recent_crawls"] = query("""
        SELECT checked_at AT TIME ZONE 'UTC' AS checked_at,
               http_status, response_time_ms, success, error_message
        FROM crawl_log WHERE agent_id = %s::uuid ORDER BY checked_at DESC LIMIT 5
    """, [agent_id])
    return json.dumps(agent, default=str)


@_mcp.tool()
def submit_domain(domain: str) -> str:
    """
    Submit a domain to the Chiwawa crawler queue.
    The crawler will check /.well-known/agent.json on that domain for an A2A agent card.

    Args:
        domain: Domain to crawl, e.g. 'example.com' — no https://, no trailing slash.
    """
    domain = domain.strip().lower()
    if not domain or not DOMAIN_RE.match(domain):
        return json.dumps({"error": "Invalid domain name"})
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO seed_domains (domain, source, status) VALUES (%s, 'mcp_submission', 'pending') ON CONFLICT (domain) DO NOTHING",
            (domain,),
        )
        inserted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return json.dumps({
            "domain": domain,
            "queued": inserted,
            "message": "Added to crawl queue." if inserted else "Domain already known.",
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


app.mount("/mcp", _mcp.sse_app())
