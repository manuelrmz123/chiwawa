import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

cur.execute("""
    SELECT DATE(called_at) AS day, endpoint, COUNT(*) AS calls
    FROM api_calls
    GROUP BY 1, 2
    ORDER BY 1 DESC, 3 DESC
""")
rows = cur.fetchall()
conn.close()

if not rows:
    print("No API calls recorded yet.")
else:
    print(f"{'Day':<12} {'Endpoint':<20} {'Calls':>5}")
    print("-" * 40)
    for day, endpoint, calls in rows:
        print(f"{str(day):<12} {endpoint:<20} {calls:>5}")
