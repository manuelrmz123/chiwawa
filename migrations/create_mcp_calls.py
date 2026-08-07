import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS mcp_calls (
        id        BIGSERIAL PRIMARY KEY,
        called_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        tool_name TEXT        NOT NULL,
        success   BOOLEAN     NOT NULL DEFAULT TRUE
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS mcp_calls_called_at_idx ON mcp_calls (called_at DESC)")
cur.execute("CREATE INDEX IF NOT EXISTS mcp_calls_tool_name_idx ON mcp_calls (tool_name)")
conn.commit()
cur.execute("SELECT COUNT(*) FROM mcp_calls")
print("Table ready. Rows:", cur.fetchone()[0])
conn.close()
