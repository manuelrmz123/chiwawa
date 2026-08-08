import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

cur.execute("""
    SELECT called_at AT TIME ZONE 'UTC' AS called_at,
           tool_name, success, ip, user_agent
    FROM mcp_calls
    ORDER BY called_at DESC
    LIMIT 50
""")
rows = cur.fetchall()
conn.close()

if not rows:
    print("No MCP calls recorded yet.")
else:
    print(f"{'Timestamp (UTC)':<22} {'Tool':<18} {'OK':<4} {'IP':<18} User-Agent")
    print("-" * 100)
    for called_at, tool, success, ip, ua in rows:
        ts = str(called_at)[:19]
        ok = "✓" if success else "✗"
        ip = (ip or "—")[:18]
        ua = (ua or "—")[:50]
        print(f"{ts:<22} {tool:<18} {ok:<4} {ip:<18} {ua}")
