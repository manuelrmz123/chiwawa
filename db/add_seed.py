import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True
cur = conn.cursor()
cur.execute(
    "INSERT INTO seed_domains (domain, source, status) VALUES (%s, 'manual', 'pending') ON CONFLICT (domain) DO NOTHING",
    ("chiwawa.vercel.app",)
)
print("Added chiwawa.vercel.app to seed list")
conn.close()
