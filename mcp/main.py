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


def _run_source(label: str, fn, db_url: str) -> tuple[int, int]:
    """Run one ingestion source in isolation — a crash here must not stop
    the remaining sources from running."""
    try:
        return fn(db_url)
    except Exception as e:
        print(f"  {label} failed: {e}\n")
        return 0, 0


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")

    print("=== Ingestion ===\n")

    print("[1/5] Smithery Registry...")
    s_new, s_updated = _run_source("Smithery Registry", smithery.run, db_url)
    print(f"  Done. New: {s_new}, Updated: {s_updated}\n")

    print("[2/5] GitHub MCP Search...")
    g_new, g_updated = _run_source("GitHub MCP Search", github_search.run, db_url)
    print(f"  Done. New: {g_new}, Updated: {g_updated}\n")

    print("[3/5] HuggingFace Spaces...")
    h_new, h_updated = _run_source("HuggingFace Spaces", hf_spaces.run, db_url)
    print(f"  Done. New: {h_new}, Updated: {h_updated}\n")

    print("[4/5] Awesome Lists...")
    a_new_agents, a_new_domains = _run_source("Awesome Lists", awesome_lists.run, db_url)
    print(f"  Done. New agents: {a_new_agents}, New seed domains: {a_new_domains}\n")

    print("[5/5] npm Registry...")
    n_new, n_updated = _run_source("npm Registry", npm_registry.run, db_url)
    print(f"  Done. New: {n_new}, Updated: {n_updated}\n")

    total_new = s_new + g_new + h_new + a_new_agents + n_new
    total_updated = s_updated + g_updated + h_updated + n_updated
    print(f"=== Ingestion complete — {total_new} new agents, {total_updated} updated, {a_new_domains} new domains seeded ===")


if __name__ == "__main__":
    main()
