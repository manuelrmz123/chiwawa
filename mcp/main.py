import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

import smithery
import github_search
import hf_spaces
import awesome_lists
import npm_registry


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")

    print("=== Ingestion ===\n")

    print("[1/4] Smithery Registry...")
    s_new, s_updated = smithery.run(db_url)
    print(f"  Done. New: {s_new}, Updated: {s_updated}\n")

    print("[2/4] GitHub MCP Search...")
    g_new, g_updated = github_search.run(db_url)
    print(f"  Done. New: {g_new}, Updated: {g_updated}\n")

    print("[3/4] HuggingFace Spaces...")
    h_new, h_updated = hf_spaces.run(db_url)
    print(f"  Done. New: {h_new}, Updated: {h_updated}\n")

    print("[4/5] Awesome Lists...")
    a_new_agents, a_new_domains = awesome_lists.run(db_url)
    print(f"  Done. New agents: {a_new_agents}, New seed domains: {a_new_domains}\n")

    print("[5/5] npm Registry...")
    n_new, n_updated = npm_registry.run(db_url)
    print(f"  Done. New: {n_new}, Updated: {n_updated}\n")

    total_new = s_new + g_new + h_new + a_new_agents + n_new
    total_updated = s_updated + g_updated + h_updated + n_updated
    print(f"=== Ingestion complete — {total_new} new agents, {total_updated} updated, {a_new_domains} new domains seeded ===")


if __name__ == "__main__":
    main()
