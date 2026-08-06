import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

import smithery
import github_search


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")

    print("=== Phase 2: MCP Ingestion ===\n")

    print("[1/2] Smithery Registry...")
    s_new, s_updated = smithery.run(db_url)
    print(f"  Done. New: {s_new}, Updated: {s_updated}\n")

    print("[2/2] GitHub MCP Search...")
    g_new, g_updated = github_search.run(db_url)
    print(f"  Done. New: {g_new}, Updated: {g_updated}\n")

    total_new = s_new + g_new
    total_updated = s_updated + g_updated
    print(f"=== Ingestion complete — {total_new} new agents, {total_updated} updated ===")


if __name__ == "__main__":
    main()
