"""Probe a few awesome lists to understand URL patterns."""
import urllib.request, re

LISTS = [
    "punkpeye/awesome-mcp-servers",
    "e2b-dev/awesome-ai-agents",
    "wong2/awesome-mcp-servers",
]

MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)]+)\)')

for repo in LISTS:
    url = f"https://raw.githubusercontent.com/{repo}/main/README.md"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Chiwawa-Crawler/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        links = MD_LINK.findall(text)
        github = [u for _, u in links if "github.com" in u]
        external = [u for _, u in links if "github.com" not in u and "shields.io" not in u and "img.shields" not in u]
        print(f"\n{repo}: {len(links)} links total")
        print(f"  GitHub:   {len(github)} — e.g. {github[:2]}")
        print(f"  External: {len(external)} — e.g. {external[:2]}")
    except Exception as e:
        print(f"{repo}: ERROR {e}")
