"""Probe Dify marketplace - try multiple known endpoint patterns."""
import urllib.request, json

ENDPOINTS = [
    "https://marketplace.dify.ai/api/v1/plugins?page=1&page_size=3&sort_by=install_count&sort_order=DESC",
    "https://marketplace.dify.ai/api/v1/plugins?page=1&page_size=3",
    "https://marketplace.dify.ai/api/v1/categories",
    "https://cloud.dify.ai/api/v1/explore/apps?page=1&page_size=3",
    "https://udify.app/api/v1/explore/apps?page=1&page_size=3",
]

for url in ENDPOINTS:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            print(f"\nOK {url}")
            print(f"  {raw[:300]}")
    except Exception as e:
        print(f"\nFAIL {url}: {e}")
