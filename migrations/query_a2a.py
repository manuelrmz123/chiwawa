import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
import os, psycopg2, json
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("""
    SELECT name, description, base_url, status, first_seen_at
    FROM agents WHERE type = 'a2a' ORDER BY first_seen_at
""")
rows = cur.fetchall()
print(f"Total A2A agents: {len(rows)}\n")
print(f"{'#':<4} {'Name':<30} {'Status':<10} {'First Seen':<22} URL")
print("-" * 110)
for i, (name, desc, base_url, status, first_seen) in enumerate(rows, 1):
    ts = str(first_seen)[:10]
    print(f"{i:<4} {(name or '-'):<30} {status:<10} {ts:<22} {base_url or '-'}")
    if desc:
        print(f"     {desc[:100]}")
    print()
conn.close()
