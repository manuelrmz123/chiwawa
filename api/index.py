import json
import os
import re
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


# ---------------------------------------------------------------------------
# Routes
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
    by_status = query("""
        SELECT status, COUNT(*) AS count FROM agents
        GROUP BY status ORDER BY count DESC
    """)
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
    return jsn({
        "totals": totals,
        "by_status": by_status,
        "recent_agents": recent,
        "recent_crawls": crawls,
        "seed_stats": seeds,
    })


@app.get("/agents")
def list_agents(
    type: str = Query(None, description="Filter by type: a2a, mcp_live, mcp_package"),
    status: str = Query(None, description="Filter by status: active, degraded, unresponsive, unreachable, gone, archived"),
    search: str = Query(None, description="Search by name or description (case-insensitive)"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    conditions, params = [], []

    if type:
        conditions.append("type = %s")
        params.append(type)
    if status:
        conditions.append("status = %s")
        params.append(status)
    if search:
        conditions.append("(name ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * limit

    total = query(f"SELECT COUNT(*) AS n FROM agents {where}", params)[0]["n"]
    agents = query(f"""
        SELECT id::text, type, name, description, base_url, provider_name,
               status, version, consecutive_fails, dns_resolves, ssl_valid,
               last_http_status, last_seen_at, last_checked_at, first_seen_at
        FROM agents {where}
        ORDER BY first_seen_at DESC
        LIMIT %s OFFSET %s
    """, params + [limit, offset])

    return jsn({
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
        "agents": agents,
    })


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
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
        "SELECT skill_id, name, description, tags, examples FROM agent_skills WHERE agent_id = %s::uuid",
        [agent_id]
    )
    agent["auth_schemes"] = [r["scheme"] for r in query(
        "SELECT scheme FROM agent_auth_schemes WHERE agent_id = %s::uuid", [agent_id]
    )]
    agent["io_modes"] = query(
        "SELECT direction, mime_type FROM agent_io_modes WHERE agent_id = %s::uuid",
        [agent_id]
    )
    return jsn(agent)


@app.get("/agents/{agent_id}/history")
def get_history(agent_id: str):
    rows = query("""
        SELECT id::text, changed_at, previous_hash, new_hash, previous_card, new_card
        FROM agent_card_history
        WHERE agent_id = %s::uuid
        ORDER BY changed_at DESC
    """, [agent_id])
    return jsn(rows)


@app.get("/agents/{agent_id}/crawl_log")
def get_crawl_log(agent_id: str):
    rows = query("""
        SELECT id::text, domain, checked_at, http_status, response_time_ms, success, error_message
        FROM crawl_log
        WHERE agent_id = %s::uuid
        ORDER BY checked_at DESC
        LIMIT 20
    """, [agent_id])
    return jsn(rows)


# In-memory rate limiter for submissions (resets on cold start — good enough for a pet project)
_submissions: dict[str, list] = defaultdict(list)

DOMAIN_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$')


@app.post("/submissions", status_code=201)
def submit_domain(request: Request, body: dict):
    domain = body.get("domain", "").strip().lower()

    if not domain or not DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail="Invalid domain name")

    ip = request.client.host
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
