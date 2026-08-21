import hashlib
import json
import os
import time
import urllib.request
import urllib.parse
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

API_BASE = "https://huggingface.co/api/spaces"
PAGE_SIZE = 500

# Tags to crawl in priority order. mcp-server first since those overlap with
# our existing coverage and are highest signal. Others broaden to general agents.
TAGS = ["mcp-server", "agent", "llm-agent", "ai-agent", "chatbot"]


def compute_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def fetch_page(tag: str, page: int) -> list:
    params = urllib.parse.urlencode({
        "limit": PAGE_SIZE,
        "filter": tag,
        "sort": "likes",
        "direction": -1,
        "p": page,
        "full": "true",
    })
    req = urllib.request.Request(
        f"{API_BASE}?{params}",
        headers={"User-Agent": "Chiwawa-Crawler/0.1"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def space_to_agent(space: dict) -> dict:
    space_id = space["id"]           # "author/space-name"
    author = space.get("author", "")
    card = space.get("cardData") or {}
    subdomain = space.get("subdomain")

    name = card.get("title") or space_id
    description = card.get("description") or card.get("short_description") or ""
    base_url = f"https://huggingface.co/spaces/{space_id}"
    live_url = f"https://{subdomain}.hf.space" if subdomain else None

    raw_card = {
        "id": space_id,
        "author": author,
        "sdk": space.get("sdk"),
        "tags": space.get("tags", []),
        "likes": space.get("likes", 0),
        "trendingScore": space.get("trendingScore", 0),
        "createdAt": space.get("createdAt"),
        "lastModified": space.get("lastModified"),
        "subdomain": subdomain,
        "live_url": live_url,
        "cardData": card,
    }

    return {
        "name": name,
        "description": description,
        "base_url": base_url,
        "card_url": base_url,          # dedup key — HF space page URL
        "live_url": live_url,
        "provider_name": author,
        "raw_card": raw_card,
        "private": space.get("private", False),
    }


def upsert(conn, agent: dict) -> str:
    raw_card = agent["raw_card"]
    card_hash = compute_hash(raw_card)
    card_url = agent["card_url"]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, card_hash FROM agents WHERE card_url = %s AND type = 'hf_space'",
            (card_url,)
        )
        existing = cur.fetchone()

        if existing:
            agent_id, old_hash = str(existing[0]), existing[1]
            if old_hash != card_hash:
                cur.execute("""
                    INSERT INTO agent_card_history
                        (agent_id, changed_at, previous_hash, new_hash, previous_card, new_card)
                    SELECT id, now(), %s, %s, raw_card, %s::jsonb
                    FROM agents WHERE id = %s
                """, (old_hash, card_hash, json.dumps(raw_card), agent_id))

                cur.execute("""
                    UPDATE agents SET
                        name = %s, description = %s, provider_name = %s,
                        raw_card = %s::jsonb, card_hash = %s,
                        last_seen_at = now(), last_checked_at = now()
                    WHERE id = %s
                """, (
                    agent["name"], agent["description"], agent["provider_name"],
                    json.dumps(raw_card), card_hash, agent_id
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
                    'hf_space', %s, %s, %s, %s, %s,
                    %s::jsonb, %s, 'active', 0,
                    true, true,
                    now(), now(), now()
                ) RETURNING id
            """, (
                agent["name"], agent["description"],
                agent["base_url"], card_url, agent["provider_name"],
                json.dumps(raw_card), card_hash,
            ))
            agent_id = str(cur.fetchone()[0])
            action = "new"

        cur.execute("""
            INSERT INTO crawl_log
                (agent_id, domain, checked_at, http_status, response_time_ms, success, card_hash)
            VALUES (%s, %s, now(), 200, null, true, %s)
        """, (agent_id, agent["raw_card"]["id"], card_hash))

    conn.commit()
    return action


def run(db_url: str) -> tuple[int, int]:
    new_count = updated_count = 0
    seen_ids: set[str] = set()

    for tag in TAGS:
        print(f"  Tag: '{tag}'")
        page = 0

        while True:
            try:
                spaces = fetch_page(tag, page)
            except urllib.error.HTTPError as e:
                print(f"    HTTP {e.code} on page {page}, stopping tag.")
                break
            except Exception as e:
                print(f"    Error on page {page}: {e}, stopping tag.")
                break

            if not spaces:
                break

            batch_new = batch_updated = batch_skipped = 0
            conn = psycopg2.connect(db_url)

            for space in spaces:
                space_id = space.get("id", "")

                # Skip private spaces and already-seen IDs (cross-tag dedup)
                if space.get("private") or space_id in seen_ids:
                    batch_skipped += 1
                    continue
                seen_ids.add(space_id)

                agent = space_to_agent(space)
                try:
                    action = upsert(conn, agent)
                except psycopg2.OperationalError:
                    # Reconnect on Neon idle timeout and retry once
                    conn.close()
                    conn = psycopg2.connect(db_url)
                    action = upsert(conn, agent)

                if action == "new":
                    batch_new += 1
                    new_count += 1
                else:
                    batch_updated += 1
                    updated_count += 1

            conn.close()
            print(f"    Page {page}: {len(spaces)} spaces — {batch_new} new, {batch_updated} updated, {batch_skipped} skipped")

            # HF API returns the same set when pagination is exhausted — stop
            # when an entire page is duplicates and we're past page 0.
            if len(spaces) < PAGE_SIZE or (page > 0 and batch_new == 0 and batch_updated == 0):
                break
            page += 1
            time.sleep(1)

        time.sleep(2)

    return new_count, updated_count
