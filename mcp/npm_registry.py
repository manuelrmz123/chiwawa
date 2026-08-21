import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.parse
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
PAGE_SIZE = 250  # npm API max

# Search queries — we client-side filter to reduce noise
QUERIES = [
    "keywords:mcp-server",
    "keywords:model-context-protocol",
    "keywords:llm-agent",
    "keywords:ai-agent",
]

# Package must have at least one of these in its keywords array to be kept
REQUIRED_KEYWORDS = {
    "mcp", "mcp-server", "model-context-protocol", "modelcontextprotocol",
    "ai-agent", "llm-agent", "agent", "llm", "mcp-client",
}

GH_REPO = re.compile(r'github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:\.git|/|$)')
DOMAIN_RE = re.compile(r'^https?://(?:www\.)?([^/?#]+)')
SKIP_DOMAINS = {
    "github.com", "npmjs.com", "nodejs.org", "shields.io",
    "githubusercontent.com", "twitter.com", "discord.com",
}


def compute_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def fetch_page(query: str, offset: int) -> dict:
    params = urllib.parse.urlencode({"text": query, "size": PAGE_SIZE, "from": offset})
    req = urllib.request.Request(
        f"{SEARCH_URL}?{params}",
        headers={"User-Agent": "Chiwawa-Crawler/0.1"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def is_relevant(pkg: dict) -> bool:
    keywords = {k.lower() for k in pkg.get("keywords", [])}
    return bool(keywords & REQUIRED_KEYWORDS)


def upsert_agent(conn, pkg: dict) -> str:
    name = pkg.get("name", "")
    card_url = f"https://www.npmjs.com/package/{name}"
    links = pkg.get("links", {})
    repo_url = links.get("repository", "")
    homepage = links.get("homepage", "")

    # Prefer GitHub repo URL as base_url, fall back to npm page
    gh_match = GH_REPO.search(repo_url or "")
    if gh_match:
        base_url = f"https://github.com/{gh_match.group(1)}"
    else:
        base_url = homepage or card_url

    raw_card = {
        "name": name,
        "description": pkg.get("description", ""),
        "keywords": pkg.get("keywords", []),
        "version": pkg.get("version"),
        "links": links,
        "publisher": pkg.get("publisher", {}).get("username", ""),
        "date": pkg.get("date"),
    }
    card_hash = compute_hash(raw_card)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, card_hash FROM agents WHERE card_url = %s AND type = 'mcp_package'",
            (card_url,)
        )
        existing = cur.fetchone()

        if existing:
            agent_id, old_hash = str(existing[0]), existing[1]
            if old_hash != card_hash:
                cur.execute("""
                    INSERT INTO agent_card_history
                        (agent_id, changed_at, previous_hash, new_hash, previous_card, new_card)
                    SELECT id, now(), %s, %s, raw_card, %s::jsonb FROM agents WHERE id = %s
                """, (old_hash, card_hash, json.dumps(raw_card), agent_id))
                cur.execute("""
                    UPDATE agents SET name=%s, description=%s, raw_card=%s::jsonb,
                        card_hash=%s, last_seen_at=now(), last_checked_at=now()
                    WHERE id=%s
                """, (name, pkg.get("description",""), json.dumps(raw_card), card_hash, agent_id))
            action = "updated"
        else:
            cur.execute("""
                INSERT INTO agents (
                    type, name, description, base_url, card_url, provider_name,
                    raw_card, card_hash, status, consecutive_fails,
                    dns_resolves, ssl_valid, last_seen_at, last_checked_at, first_seen_at
                ) VALUES (
                    'mcp_package', %s, %s, %s, %s, %s,
                    %s::jsonb, %s, 'active', 0, true, true, now(), now(), now()
                ) ON CONFLICT DO NOTHING RETURNING id
            """, (
                name, pkg.get("description", ""), base_url, card_url,
                pkg.get("publisher", {}).get("username", ""),
                json.dumps(raw_card), card_hash,
            ))
            action = "new" if cur.fetchone() else "existing"

        cur.execute("""
            INSERT INTO crawl_log (agent_id, domain, checked_at, http_status, response_time_ms, success, card_hash)
            VALUES ((SELECT id FROM agents WHERE card_url=%s), %s, now(), 200, null, true, %s)
        """, (card_url, name, card_hash))

    conn.commit()
    return action


def upsert_seed_domain(conn, domain: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO seed_domains (domain, source, status, consecutive_fails)
            VALUES (%s, 'npm_registry', 'pending', 0)
            ON CONFLICT (domain) DO NOTHING
        """, (domain,))
    conn.commit()


def run(db_url: str) -> tuple[int, int]:
    new_count = updated_count = 0
    seen_names: set[str] = set()

    for query in QUERIES:
        print(f"  Query: '{query}'")
        offset = 0
        page = 0

        while True:
            try:
                data = fetch_page(query, offset)
            except Exception as e:
                print(f"    Error on page {page}: {e}, stopping.")
                break

            objects = data.get("objects", [])
            if not objects:
                break

            total = data.get("total", 0)
            conn = psycopg2.connect(db_url)
            batch_new = batch_updated = batch_skipped = batch_irrelevant = 0

            for obj in objects:
                pkg = obj.get("package", {})
                name = pkg.get("name", "")

                if name in seen_names:
                    batch_skipped += 1
                    continue

                if not is_relevant(pkg):
                    batch_irrelevant += 1
                    seen_names.add(name)
                    continue

                seen_names.add(name)

                # Also seed non-GitHub homepages for A2A probe
                homepage = pkg.get("links", {}).get("homepage", "")
                if homepage and "github.com" not in homepage:
                    domain_match = DOMAIN_RE.match(homepage)
                    if domain_match:
                        domain = domain_match.group(1)
                        if domain not in SKIP_DOMAINS:
                            try:
                                upsert_seed_domain(conn, domain)
                            except Exception:
                                pass

                try:
                    action = upsert_agent(conn, pkg)
                except psycopg2.OperationalError:
                    conn.close()
                    conn = psycopg2.connect(db_url)
                    action = upsert_agent(conn, pkg)

                if action == "new":
                    batch_new += 1
                    new_count += 1
                elif action == "updated":
                    batch_updated += 1
                    updated_count += 1

            conn.close()
            print(f"    Page {page} (offset {offset}, total {total}): "
                  f"{batch_new} new, {batch_updated} updated, "
                  f"{batch_skipped} skipped, {batch_irrelevant} filtered")

            # npm caps at 5000 results; stop when page is partial or limit hit
            if len(objects) < PAGE_SIZE or offset + PAGE_SIZE >= 5000:
                break
            offset += PAGE_SIZE
            page += 1
            time.sleep(1)

        time.sleep(2)

    return new_count, updated_count
