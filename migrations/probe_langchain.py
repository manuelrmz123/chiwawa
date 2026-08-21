"""Probe LangChain Hub API."""
import urllib.request, json

ENDPOINTS = [
    "https://api.hub.langchain.com/repos?limit=3&sort_field=num_downloads&sort_direction=desc",
    "https://api.hub.langchain.com/repos?limit=3&tags=agent",
]

for url in ENDPOINTS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Chiwawa-Crawler/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        print(f"\nOK: {url}")
        print(f"  Keys: {list(data.keys())}")
        repos = data.get("repos", [])
        print(f"  Count: {len(repos)}, total: {data.get('total_count')}")
        if repos:
            r = repos[0]
            print(f"  Sample: full_name={r.get('full_name')} tags={r.get('tags',[])} downloads={r.get('num_downloads')}")
    except Exception as e:
        print(f"\nFAIL {url}: {e}")
