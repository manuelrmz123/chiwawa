"""Add 'hf_space' to the agents.type CHECK constraint."""
from dotenv import load_dotenv
import os, psycopg2

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Find the constraint name
cur.execute("""
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'agents'::regclass AND contype = 'c' AND conname LIKE '%type%'
""")
rows = cur.fetchall()
print('Type constraints found:', rows)

# Drop and recreate with hf_space included
for (conname,) in rows:
    cur.execute(f"ALTER TABLE agents DROP CONSTRAINT {conname}")
    print(f"Dropped: {conname}")

cur.execute("""
    ALTER TABLE agents ADD CONSTRAINT agents_type_check
    CHECK (type IN ('mcp_package', 'mcp_live', 'a2a', 'hf_space'))
""")
print("Added new constraint with hf_space.")

conn.commit()
conn.close()
