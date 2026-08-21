"""Probe PyPI search HTML structure."""
import urllib.request, urllib.parse, re

params = urllib.parse.urlencode({"q": "mcp-server", "o": "-zscore"})
req = urllib.request.Request(
    f"https://pypi.org/search/?{params}",
    headers={"User-Agent": "Mozilla/5.0 Chiwawa-Crawler/0.1"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode("utf-8", errors="ignore")

# PyPI search results are in <a class="package-snippet"> tags
snippets = re.findall(r'<a class="package-snippet"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
print(f"Found {len(snippets)} snippets on page 1")

# Extract name, version, description from each snippet
NAME = re.compile(r'<span class="package-snippet__name">([^<]+)</span>')
VER  = re.compile(r'<span class="package-snippet__version">([^<]+)</span>')
DESC = re.compile(r'<p class="package-snippet__description">([^<]*)</p>')

for href, body in snippets[:5]:
    name = NAME.search(body)
    ver  = VER.search(body)
    desc = DESC.search(body)
    print(f"  {name.group(1) if name else '?'} {ver.group(1) if ver else ''} — {desc.group(1).strip() if desc else ''}")

# Check if there are multiple pages
total = re.search(r'(\d[\d,]*)\s+projects', html)
print(f"\nTotal projects: {total.group(1) if total else 'unknown'}")
pages = re.findall(r'page=(\d+)', html)
print(f"Page links found: {sorted(set(pages))}")
