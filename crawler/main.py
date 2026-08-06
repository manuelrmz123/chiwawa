import asyncio
import os
import psycopg2
from dotenv import load_dotenv

from fetcher import fetch_agent_card
from storage import (
    get_connection, get_pending_domains, upsert_agent,
    log_crawl, update_seed_domain, compute_hash
)

load_dotenv()

MAX_CONCURRENT = 10


async def crawl_domain(domain_info: dict, db_url: str, semaphore: asyncio.Semaphore):
    domain_id = domain_info["id"]
    domain = domain_info["domain"]

    async with semaphore:
        result = await fetch_agent_card(domain)

    conn = get_connection(db_url)
    try:
        agent_id = upsert_agent(conn, result)
        card_hash = compute_hash(result["card"]) if result.get("card") else None
        log_crawl(conn, result, agent_id, card_hash)

        with conn.cursor() as cur:
            cur.execute("SELECT consecutive_fails FROM seed_domains WHERE id = %s", (domain_id,))
            row = cur.fetchone()
            current_fails = row[0] if row else 0

        update_seed_domain(conn, domain_id, result["success"], current_fails)
    finally:
        conn.close()

    status = "FOUND" if result["success"] else f"MISS ({result.get('error', 'unknown')})"
    print(f"  {domain}: {status}")


async def run_crawl():
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")

    conn = get_connection(db_url)
    domains = get_pending_domains(conn, limit=100)
    conn.close()

    if not domains:
        print("No domains pending crawl.")
        return

    print(f"Crawling {len(domains)} domains...")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [crawl_domain(d, db_url, semaphore) for d in domains]
    await asyncio.gather(*tasks)
    print("Crawl complete.")


if __name__ == "__main__":
    asyncio.run(run_crawl())
