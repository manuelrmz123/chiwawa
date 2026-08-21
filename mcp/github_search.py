import hashlib
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

SEARCH_URL = "https://api.github.com/search/repositories"
QUERIES = [
    "topic:mcp-server",
    "topic:model-context-protocol",
    "topic:ai-agent",
    "topic:llm-agent",
    "topic:autonomous-agent",
]


def compute_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def fetch_search(query: str, page: int, token: str | None) -> dict:
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 100,
        "page": page,
    })
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Chiwawa-Crawler/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def upsert(conn, repo: dict) -> str:
    raw_card = {
        "id": repo["id"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "description": repo.get("description"),
        "owner": repo.get("owner", {}).get("login"),
        "language": repo.get("language"),
        "topics": repo.get("topics", []),
        "stargazers_count": repo.get("stargazers_count", 0),
        "archived": repo.get("archived", False),
        "updated_at": repo.get("updated_at"),
    }
    card_hash = compute_hash(raw_card)
    base_url = repo["html_url"]

    with conn.cursor() as cur:
        # GitHub repos have no card_url — dedup on base_url
        cur.execute(
            "SELECT id, card_hash FROM agents WHERE base_url = %s AND type = 'mcp_package' AND card_url IS NULL",
            (base_url,)
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
                    name = %s, description = %s,
                    raw_card = %s::jsonb, card_hash = %s,
                    last_seen_at = now(), last_checked_at = now()
                WHERE id = %s
            """, (
                repo.get("name", ""), repo.get("description") or "",
                json.dumps(raw_card), card_hash,
                agent_id
            ))
            action = "updated"
        else:
            status = "archived" if repo.get("archived") else "active"
            cur.execute("""
                INSERT INTO agents (
                    type, name, description, base_url, card_url, provider_name,
                    raw_card, card_hash, status, consecutive_fails,
                    dns_resolves, ssl_valid,
                    last_seen_at, last_checked_at, first_seen_at
                ) VALUES (
                    'mcp_package', %s, %s, %s, null, %s,
                    %s::jsonb, %s, %s, 0,
                    true, true,
                    now(), now(), now()
                ) RETURNING id
            """, (
                repo.get("name", ""), repo.get("description") or "",
                base_url, repo.get("owner", {}).get("login", ""),
                json.dumps(raw_card), card_hash, status
            ))
            agent_id = str(cur.fetchone()[0])
            action = "new"

        cur.execute("""
            INSERT INTO crawl_log
                (agent_id, domain, checked_at, http_status, response_time_ms, success, card_hash)
            VALUES (%s, %s, now(), null, null, true, %s)
        """, (agent_id, repo.get("full_name", base_url), card_hash))

    conn.commit()
    return action


def run(db_url: str) -> tuple[int, int]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("  Note: GITHUB_TOKEN not set — using unauthenticated (60 req/hr limit).")

    new_count = updated_count = 0
    seen_ids: set[int] = set()

    for query in QUERIES:
        print(f"  Searching: '{query}'")
        page = 1

        while True:
            try:
                data = fetch_search(query, page, token)
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    print(f"  Rate limit hit on page {page}. Stopping this query.")
                    break
                raise

            items = data.get("items", [])
            if not items:
                break

            # Fresh connection per page — avoids Neon idle timeout
            conn = psycopg2.connect(db_url)
            for repo in items:
                if repo["id"] in seen_ids:
                    continue
                seen_ids.add(repo["id"])

                action = upsert(conn, repo)
                if action == "new":
                    new_count += 1
                else:
                    updated_count += 1
            conn.close()

            total = data.get("total_count", 0)
            max_page = min((total // 100) + 1, 10)
            print(f"    Page {page}: {len(items)} repos (total available: {total})")

            if page >= max_page or len(items) < 100:
                break
            page += 1
            time.sleep(2)

        time.sleep(3)

    return new_count, updated_count
