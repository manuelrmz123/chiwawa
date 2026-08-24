from dotenv import load_dotenv
import os, psycopg2
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("ALTER TABLE api_calls ADD COLUMN IF NOT EXISTS query_params TEXT")
cur.execute("ALTER TABLE api_calls ADD COLUMN IF NOT EXISTS referer TEXT")
cur.execute("ALTER TABLE api_calls ADD COLUMN IF NOT EXISTS agent_card_url TEXT")
conn.commit()
conn.close()
print("Done.")
