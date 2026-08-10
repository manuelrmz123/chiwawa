from dotenv import load_dotenv
import os, psycopg2

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# API totals
cur.execute("SELECT COUNT(*) FROM api_calls")
api_total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM api_calls WHERE called_at >= NOW() - INTERVAL '24 hours'")
api_today = cur.fetchone()[0]
cur.execute("SELECT MIN(called_at), MAX(called_at) FROM api_calls")
api_range = cur.fetchone()

# MCP totals
cur.execute("SELECT COUNT(*) FROM mcp_calls")
mcp_total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM mcp_calls WHERE called_at >= NOW() - INTERVAL '24 hours'")
mcp_today = cur.fetchone()[0]
cur.execute("SELECT MIN(called_at), MAX(called_at) FROM mcp_calls")
mcp_range = cur.fetchone()

# Top endpoints
cur.execute("SELECT endpoint, COUNT(*) FROM api_calls GROUP BY endpoint ORDER BY COUNT(*) DESC")
api_endpoints = cur.fetchall()

# Top MCP tools
cur.execute("SELECT tool_name, COUNT(*) FROM mcp_calls GROUP BY tool_name ORDER BY COUNT(*) DESC")
mcp_tools = cur.fetchall()

# Recent API calls
cur.execute("""
    SELECT called_at AT TIME ZONE 'UTC', endpoint, ip, user_agent
    FROM api_calls ORDER BY called_at DESC LIMIT 20
""")
api_recent = cur.fetchall()

# Recent MCP calls
cur.execute("""
    SELECT called_at AT TIME ZONE 'UTC', tool_name, success, ip, user_agent
    FROM mcp_calls ORDER BY called_at DESC LIMIT 20
""")
mcp_recent = cur.fetchall()

conn.close()

print("=== API CALLS ===")
print(f"Total: {api_total}  |  Last 24h: {api_today}")
print(f"First: {api_range[0]}  |  Last: {api_range[1]}")
print()
print("By endpoint:")
for ep, cnt in api_endpoints:
    print(f"  {ep:<25} {cnt}")
print()
print("Recent (last 20):")
print(f"{'Timestamp (UTC)':<22} {'Endpoint':<18} {'IP':<18} User-Agent")
print("-" * 110)
for r in api_recent:
    ts = str(r[0])[:19]
    ep = (r[1] or "-")[:18]
    ip = (r[2] or "-")[:18]
    ua = (r[3] or "-")[:55]
    print(f"{ts:<22} {ep:<18} {ip:<18} {ua}")

print()
print("=== MCP CALLS ===")
print(f"Total: {mcp_total}  |  Last 24h: {mcp_today}")
print(f"First: {mcp_range[0]}  |  Last: {mcp_range[1]}")
print()
print("By tool:")
for tool, cnt in mcp_tools:
    print(f"  {tool:<28} {cnt}")
print()
print("Recent (last 20):")
print(f"{'Timestamp (UTC)':<22} {'Tool':<20} {'OK':<6} {'IP':<18} User-Agent")
print("-" * 110)
for r in mcp_recent:
    ts = str(r[0])[:19]
    tool = (r[1] or "-")[:20]
    ok = "OK" if r[2] else "FAIL"
    ip = (r[3] or "-")[:18]
    ua = (r[4] or "-")[:45]
    print(f"{ts:<22} {tool:<20} {ok:<6} {ip:<18} {ua}")
