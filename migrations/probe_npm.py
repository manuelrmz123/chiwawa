"""Probe npm keyword search to find focused result counts."""
import urllib.request, urllib.parse, json

# Use keywords: prefix to filter by package keyword tags, not full text
QUERIES = [
    "keywords:mcp-server",
    "keywords:mcp",
    "keywords:model-context-protocol",
    "keywords:ai-agent",
    "keywords:llm-agent",
]

for q in QUERIES:
    params = urllib.parse.urlencode({"text": q, "size": 2})
    req = urllib.request.Request(
        f"https://registry.npmjs.org/-/v1/search?{params}",
        headers={"User-Agent": "Chiwawa-Crawler/0.1"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    total = data.get("total", 0)
    samples = [o["package"]["name"] for o in data["objects"][:2]]
    print(f"  {q:<40} total={total:<8} samples={samples}")
