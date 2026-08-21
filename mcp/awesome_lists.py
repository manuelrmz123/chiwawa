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

# Awesome lists to crawl — (repo, agent_type_hint)
AWESOME_LISTS = [
    ("punkpeye/awesome-mcp-servers",    "mcp_package"),
    ("wong2/awesome-mcp-servers",        "mcp_package"),
    ("appcypher/awesome-mcp-servers",    "mcp_package"),
    ("modelcontextprotocol/servers",     "mcp_package"),
    ("e2b-dev/awesome-ai-agents",        "mcp_package"),
    ("slavakurilyak/awesome-ai-agents",  "mcp_package"),
    ("AgentOps-AI/awesome-agents",       "mcp_package"),
    ("kyrolabs/awesome-langchain",       "mcp_package"),
]

# Domains to skip when seeding — noise, CDNs, badge services, etc.
SKIP_DOMAINS = {
    "shields.io", "img.shields.io", "github.com", "githubusercontent.com",
    "twitter.com", "x.com", "linkedin.com", "youtube.com", "discord.com",
    "discord.gg", "t.co", "bit.ly", "npmjs.com", "pypi.org", "crates.io",
    "docs.rs", "pkg.go.dev", "medium.com", "dev.to", "substack.com",
    "opensource.org", "creativecommons.org", "choosealicense.com",
    "forms.gle", "google.com", "notion.so", "airtable.com",
}

MD_LINK = re.compile(r'\[(?:[^\]]*)\]\((https?://[^)]+)\)')
# Matches exactly github.com/owner/repo — no deeper paths
GH_REPO = re.compile(r'^https?://github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:/|$)')
DOMAIN_RE = re.compile(r'^https?://([^/?#]+)')


def compute_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def fetch_readme(repo: str) -> str | None:
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/README.md"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Chiwawa-Crawler/0.1"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
    return None


def extract_urls(text: str) -> tuple[set[str], set[str]]:
    """Returns (github_full_names, external_domains)."""
    github_repos: set[str] = set()
    external_domains: set[str] = set()

    for url in MD_LINK.findall(text):
        url = url.strip().rstrip(")")
        gh_match = GH_REPO.match(url)
        if gh_match:
            full_name = gh_match.group(1).rstrip(".")
            # Skip the awesome list repos themselves and obvious non-agent repos
            if "/" in full_name:
                github_repos.add(full_name)
        else:
            domain_match = DOMAIN_RE.match(url)
            if domain_match:
                domain = domain_match.group(1).lower().lstrip("www.")
                if domain not in SKIP_DOMAINS and "." in domain:
                    external_domains.add(domain)

    return github_repos, external_domains


def upsert_github_repo(conn, full_name: str, agent_type: str) -> str:
    base_url = f"https://github.com/{full_name}"
    name = full_name.split("/")[-1].replace("-", " ").replace("_", " ").title()
    raw_card = {"full_name": full_name, "html_url": base_url, "source": "awesome_list"}
    card_hash = compute_hash(raw_card)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM agents WHERE base_url = %s AND card_url IS NULL",
            (base_url,)
        )
        if cur.fetchone():
            return "existing"

        cur.execute("""
            INSERT INTO agents (
                type, name, description, base_url, card_url, provider_name,
                raw_card, card_hash, status, consecutive_fails,
                dns_resolves, ssl_valid,
                last_seen_at, last_checked_at, first_seen_at
            ) VALUES (
                %s, %s, %s, %s, null, %s,
                %s::jsonb, %s, 'active', 0,
                true, true,
                now(), now(), now()
            ) ON CONFLICT DO NOTHING RETURNING id
        """, (
            agent_type, name, "",
            base_url, full_name.split("/")[0],
            json.dumps(raw_card), card_hash,
        ))
        row = cur.fetchone()

    conn.commit()
    return "new" if row else "existing"


def upsert_seed_domain(conn, domain: str, source: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO seed_domains (domain, source, status, consecutive_fails)
            VALUES (%s, %s, 'pending', 0)
            ON CONFLICT (domain) DO NOTHING
        """, (domain, source))
    conn.commit()


def run(db_url: str) -> tuple[int, int]:
    """Returns (new_agents, new_seed_domains)."""
    new_agents = 0
    new_domains = 0
    seen_repos: set[str] = set()
    seen_domains: set[str] = set()

    for repo, agent_type in AWESOME_LISTS:
        print(f"  {repo}")
        readme = fetch_readme(repo)
        if not readme:
            print(f"    Could not fetch README, skipping.")
            continue

        github_repos, external_domains = extract_urls(readme)
        print(f"    Found {len(github_repos)} GitHub repos, {len(external_domains)} external domains")

        for full_name in github_repos:
            if full_name in seen_repos:
                continue
            seen_repos.add(full_name)
            conn = psycopg2.connect(db_url)
            try:
                action = upsert_github_repo(conn, full_name, agent_type)
            finally:
                conn.close()
            if action == "new":
                new_agents += 1

        for domain in external_domains:
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            conn = psycopg2.connect(db_url)
            try:
                upsert_seed_domain(conn, domain, f"awesome:{repo}")
            finally:
                conn.close()
            new_domains += 1

        print(f"    Done.")
        time.sleep(1)

    return new_agents, new_domains
