from dotenv import load_dotenv
import os, psycopg2
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT type, COUNT(*) FROM agents GROUP BY type ORDER BY COUNT(*) DESC")
print("By type:")
for t, c in cur.fetchall():
    print(f"  {t:<15} {c}")
cur.execute("SELECT COUNT(*) FROM agents")
print(f"Total: {cur.fetchone()[0]}")
conn.close()
