import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

cur.execute("""
    SELECT called_at AT TIME ZONE 'UTC' AS called_at,
           endpoint, ip, user_agent
    FROM api_calls
    ORDER BY called_at DESC
    LIMIT 50
""")
rows = cur.fetchall()
conn.close()

if not rows:
    print("No API calls recorded yet.")
else:
    print(f"{'Timestamp (UTC)':<22} {'Endpoint':<16} {'IP':<18} User-Agent")
    print("-" * 100)
    for called_at, endpoint, ip, ua in rows:
        ts = str(called_at)[:19]
        ip = (ip or "-")[:18]
        ua = (ua or "-")[:50]
        print(f"{ts:<22} {endpoint:<16} {ip:<18} {ua}")
