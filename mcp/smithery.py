import hashlib
import json
import os
import time
import urllib.request
import urllib.parse
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

API_BASE = "https://registry.smithery.ai/servers"
PAGE_SIZE = 50


def compute_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def fetch_page(page: int) -> dict:
    params = urllib.parse.urlencode({"page": page, "pageSize": PAGE_SIZE})
    req = urllib.request.Request(
        f"{API_BASE}?{params}",
        headers={"User-Agent": "Chiwawa-Crawler/0.1"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def upsert(conn, agent: dict) -> str:
    card_hash = compute_hash(agent["raw_card"])
    card_url = agent["card_url"]

    with conn.cursor() as cur:
        cur.execute("SELECT id, card_hash FROM agents WHERE card_url = %s", (card_url,))
        existing = cur.fetchone()

        if existing:
            agent_id, old_hash = str(existing[0]), existing[1]
            if old_hash != card_hash:
                cur.execute("""
                    INSERT INTO agent_card_history
                        (agent_id, changed_at, previous_hash, new_hash, previous_card, new_card)
                    SELECT id, now(), %s, %s, raw_card, %s::jsonb
                    FROM agents WHERE id = %s
                """, (old_hash, card_hash, json.dumps(agent["raw_card"]), agent_id))

            cur.execute("""
                UPDATE agents SET
                    name = %s, description = %s, base_url = %s, provider_name = %s,
                    raw_card = %s::jsonb, card_hash = %s,
                    last_seen_at = now(), last_checked_at = now()
                WHERE id = %s
            """, (
                agent["name"], agent["description"], agent["base_url"], agent["provider_name"],
                json.dumps(agent["raw_card"]), card_hash,
                agent_id
            ))
            action = "updated"
        else:
            cur.execute("""
                INSERT INTO agents (
                    type, name, description, base_url, card_url, provider_name,
                    raw_card, card_hash, status, consecutive_fails,
                    dns_resolves, ssl_valid,
                    last_seen_at, last_checked_at, first_seen_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, 'active', 0,
                    true, true,
                    now(), now(), now()
                ) RETURNING id
            """, (
                agent["type"], agent["name"], agent["description"],
                agent["base_url"], card_url, agent["provider_name"],
                json.dumps(agent["raw_card"]), card_hash
            ))
            agent_id = str(cur.fetchone()[0])
            action = "new"

        cur.execute("""
            INSERT INTO crawl_log
                (agent_id, domain, checked_at, http_status, response_time_ms, success, card_hash)
            VALUES (%s, %s, now(), null, null, true, %s)
        """, (agent_id, agent["domain_key"], card_hash))

    conn.commit()
    return action


def run(db_url: str) -> tuple[int, int]:
    new_count = updated_count = 0

    page = 1
    while True:
        data = fetch_page(page)
        servers = data.get("servers", [])

        if not servers:
            break

        # Fresh connection per page — avoids Neon idle timeout
        conn = psycopg2.connect(db_url)
        for s in servers:
            qname = s.get("qualifiedName", "")
            homepage = s.get("homepage") or f"https://smithery.ai/server/{qname}"

            agent = {
                "type": "mcp_live" if s.get("remote") else "mcp_package",
                "name": s.get("displayName") or qname,
                "description": s.get("description") or "",
                "base_url": homepage,
                "card_url": f"https://registry.smithery.ai/servers/{qname}",
                "provider_name": s.get("namespace") or "",
                "domain_key": qname,
                "raw_card": s,
            }

            action = upsert(conn, agent)
            if action == "new":
                new_count += 1
            else:
                updated_count += 1
        conn.close()

        print(f"  Page {page}: {len(servers)} servers processed")

        # Stop when a page returns fewer items than requested — last page reached
        if len(servers) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.5)

    return new_count, updated_count
