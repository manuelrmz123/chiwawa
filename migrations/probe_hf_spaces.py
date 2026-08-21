"""Probe HuggingFace Spaces API — pagination and volume per tag."""
import urllib.request, urllib.parse, json

def count_tag(tag, limit=500):
    """Fetch up to `limit` results for a tag and count them."""
    params = urllib.parse.urlencode({"limit": limit, "filter": tag, "sort": "likes", "direction": -1})
    req = urllib.request.Request(
        f"https://huggingface.co/api/spaces?{params}",
        headers={"User-Agent": "Chiwawa-Crawler/0.1"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return len(data), data[0] if data else None

TAGS = ["mcp-server", "agent", "chatbot", "llm-agent", "ai-agent"]

for tag in TAGS:
    count, sample = count_tag(tag)
    print(f"  tag={tag:<20} returned={count}  (limit=500, so {'MORE exist' if count==500 else 'full set'})")
    if sample:
        print(f"    top space: {sample['id']}  likes={sample.get('likes', 0)}")
