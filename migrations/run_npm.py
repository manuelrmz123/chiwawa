import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import npm_registry, psycopg2

db_url = os.environ['DATABASE_URL']
new, updated = npm_registry.run(db_url)
print(f'\nTotal — New: {new}, Updated: {updated}')

conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("SELECT type, COUNT(*) FROM agents GROUP BY type ORDER BY COUNT(*) DESC")
print('By type:')
for t, c in cur.fetchall():
    print(f'  {t:<15} {c}')
cur.execute('SELECT COUNT(*) FROM agents')
print(f'Total agents: {cur.fetchone()[0]}')
conn.close()
