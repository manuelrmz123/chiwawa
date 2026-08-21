import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
import hf_spaces
import psycopg2

db_url = os.environ['DATABASE_URL']
new, updated = hf_spaces.run(db_url)
print(f'\nTotal — New: {new}, Updated: {updated}')

conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM agents WHERE type = 'hf_space'")
print(f'hf_space agents in DB: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM agents')
print(f'Total agents in DB: {cur.fetchone()[0]}')
conn.close()
