import os
import json
import psycopg2
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")


def query(sql, params=None):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(sql, params or [])
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    conn.close()
    return [dict(zip(cols, row)) for row in rows]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file("dashboard/index.html", "text/html")
        elif parsed.path == "/data":
            self.serve_data()
        elif parsed.path == "/agents":
            self.serve_agents(parse_qs(parsed.query))
        else:
            self.send_error(404)

    def serve_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404)

    def serve_data(self):
        data = {
            "totals": query("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE type = 'a2a') AS a2a,
                    COUNT(*) FILTER (WHERE type = 'mcp_live') AS mcp_live,
                    COUNT(*) FILTER (WHERE type = 'mcp_package') AS mcp_package
                FROM agents
            """)[0],
            "by_status": query("""
                SELECT status, COUNT(*) AS count
                FROM agents
                GROUP BY status
                ORDER BY count DESC
            """),
            "recent_agents": query("""
                SELECT name, type, status, base_url,
                       first_seen_at AT TIME ZONE 'UTC' AS first_seen_at
                FROM agents
                ORDER BY first_seen_at DESC
                LIMIT 10
            """),
            "recent_crawls": query("""
                SELECT domain, checked_at AT TIME ZONE 'UTC' AS checked_at,
                       http_status, response_time_ms, success, error_message
                FROM crawl_log
                ORDER BY checked_at DESC
                LIMIT 20
            """),
            "seed_stats": query("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE next_crawl_at IS NULL) AS pending
                FROM seed_domains
            """)[0],
        }

        payload = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)


    def serve_agents(self, qs: dict):
        agent_type = qs.get("type", [None])[0]
        page = int(qs.get("page", [1])[0])
        limit = int(qs.get("limit", [50])[0])
        limit = min(limit, 500)
        offset = (page - 1) * limit

        where = "WHERE type = %s" if agent_type else ""
        params_count = [agent_type] if agent_type else []
        params_data = ([agent_type] if agent_type else []) + [limit, offset]

        total = query(f"SELECT COUNT(*) AS n FROM agents {where}", params_count)[0]["n"]
        agents = query(f"""
            SELECT name, type, status, base_url, provider_name,
                   first_seen_at AT TIME ZONE 'UTC' AS first_seen_at
            FROM agents
            {where}
            ORDER BY first_seen_at DESC
            LIMIT %s OFFSET %s
        """, params_data)

        payload = json.dumps({
            "total": total,
            "page": page,
            "limit": limit,
            "agents": agents,
        }, default=str).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = 8000
    print(f"Chiwawa dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    HTTPServer(("localhost", port), Handler).serve_forever()
