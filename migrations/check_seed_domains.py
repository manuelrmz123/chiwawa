from dotenv import load_dotenv
import os, psycopg2

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM seed_domains')
print('Total domains:', cur.fetchone()[0])

cur.execute("""
    SELECT consecutive_fails, COUNT(*) FROM seed_domains
    GROUP BY consecutive_fails ORDER BY consecutive_fails
""")
print('By fail count:')
for row in cur.fetchall():
    print(f'  fails={row[0]}: {row[1]} domains')

cur.execute("""
    SELECT COUNT(*) FROM seed_domains
    WHERE next_crawl_at IS NULL OR next_crawl_at <= now()
""")
print('Due for crawl now:', cur.fetchone()[0])

cur.execute("""
    SELECT domain, consecutive_fails, next_crawl_at
    FROM seed_domains ORDER BY consecutive_fails ASC, domain ASC
""")
print('\nAll domains:')
for row in cur.fetchall():
    next_crawl = str(row[2])[:19] if row[2] else 'NOW'
    print(f'  {row[0]:<40} fails={row[1]}  next={next_crawl}')

conn.close()
