"""Backfill agents.category for every agent that doesn't have one yet.

One-off/periodic script (Phase 1 of the Agent Trust Signals plan) — run
manually: python migrations/classify_agents.py

Deliberately not wired into the ingestion crawlers yet; re-run this script
whenever new agents are added, or once the taxonomy in api/classify.py
settles down, wire it into ingestion directly.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))
from classify import classify_agent  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


def build_text(name, description, raw_card, skills) -> str:
    # Many agents (esp. npm/GitHub-sourced) have an empty description but a
    # genuinely informative name (e.g. "fitbit-mcp-unofficial") — confirmed
    # by sampling real "other"-classified agents. The agent's own name was
    # previously missing from this blob entirely.
    parts = [name or "", description or ""]
    if isinstance(raw_card, dict):
        for key in ("keywords", "topics", "tags"):
            val = raw_card.get(key)
            if isinstance(val, list):
                parts.extend(str(v) for v in val)
    for skill_name, skill_description, tags in skills:
        if skill_name:
            parts.append(skill_name)
        if skill_description:
            parts.append(skill_description)
        if tags:
            parts.extend(tags)
    return " ".join(parts)


def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'].strip(), connect_timeout=10)
    cur = conn.cursor()

    cur.execute("SELECT id, name, description, raw_card FROM agents WHERE category IS NULL")
    rows = cur.fetchall()
    print(f"{len(rows)} agents to classify")

    counts = {}
    for i, (agent_id, name, description, raw_card) in enumerate(rows):
        cur.execute(
            "SELECT name, description, tags FROM agent_skills WHERE agent_id = %s",
            (agent_id,),
        )
        skills = cur.fetchall()

        text = build_text(name, description, raw_card, skills)
        category = classify_agent(text)

        cur.execute("UPDATE agents SET category = %s WHERE id = %s", (category, agent_id))
        counts[category] = counts.get(category, 0) + 1

        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  ...{i + 1}/{len(rows)} committed")

    conn.commit()
    conn.close()

    print("\nDistribution:")
    for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:20s} {n}")


if __name__ == "__main__":
    main()
