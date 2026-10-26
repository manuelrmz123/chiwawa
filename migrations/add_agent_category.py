"""Add 'category' column to agents (Phase 1 of the Agent Trust Signals plan).

No CHECK constraint yet on purpose — the taxonomy (see api/classify.py)
is still being tuned and shouldn't require a migration to adjust.
"""
from dotenv import load_dotenv
import os, psycopg2

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'].strip(), connect_timeout=10)
cur = conn.cursor()

cur.execute("ALTER TABLE agents ADD COLUMN IF NOT EXISTS category text")
print("Added category column (or already existed).")

conn.commit()
conn.close()
