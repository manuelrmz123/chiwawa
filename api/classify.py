"""Keyword-based agent category classifier.

Deliberately simple and deterministic (no LLM call) for v1 — see the
"Agent Trust Signals" plan. Scores each category by keyword hits against a
combined text blob (description + tags/keywords/topics + skill names), and
returns the highest-scoring category, or "other" if nothing matches.
"""

CATEGORIES = [
    "finance",
    "personal_assistant",
    "customer_support",
    "developer_tool",
    "search_research",
    "content_generation",
    "data_crawler",
    "automation",
    "other",
]

_KEYWORDS = {
    "finance": [
        "payment", "payments", "finance", "financial", "trading", "invest",
        "investment", "crypto", "cryptocurrency", "banking", "accounting",
        "budget", "budgeting", "tax", "billing", "invoice", "ledger",
        "wallet", "stripe", "fintech", "blockchain", "web3", "defi", "token",
    ],
    "personal_assistant": [
        "personal assistant", "virtual assistant", "scheduling", "calendar",
        "reminder", "reminders", "to-do", "todo", "productivity", "planner",
        "secretary", "daily tasks",
    ],
    "customer_support": [
        "customer support", "helpdesk", "help desk", "ticketing", "ticket",
        "support agent", "customer service", "faq", "live chat",
    ],
    "developer_tool": [
        "developer", "devtool", "dev tool", "coding assistant", "code review",
        "debugging", "debugger", "ci/cd", "deployment", "git ", "github",
        "sdk", "compiler", "linter", "api testing", "software engineering",
        "security", "vulnerability", "audit",
    ],
    "search_research": [
        "search engine", "web search", "research assistant", "retrieval",
        "rag", "knowledge base", "information retrieval", "fact check",
        "literature review",
    ],
    "content_generation": [
        "content generat", "copywrit", "image generat", "text generat",
        "video generat", "creative writing", "art generat", "design generat",
        # Real-world phrasing is often reversed ("generate a video/image")
        "generate image", "generate images", "generate video",
        "generate videos", "generate text", "generate a video",
        "generate an image", "text-to-image", "text-to-video",
        "image-generation", "video-generation",
    ],
    "data_crawler": [
        "crawl", "scrape", "spider", "index", "data collection", "etl",
        "data pipeline", "data extraction",
    ],
    "automation": [
        "automation", "workflow", "orchestration", "pipeline automation",
        "task automation", "rpa", "robotic process automation",
        "agent orchestration",
    ],
}


# Last-resort fallback only — applied after every specific category has
# scored zero. Virtually every entry in this registry mentions "mcp server"
# somewhere (it's the platform's own boilerplate), so if treated as a normal
# competing keyword it would win ties against genuinely specific matches
# (confirmed: an image-generation MCP server was mis-tied to developer_tool
# over content_generation). As a fallback it still correctly buckets the
# large population of generic "MCP server for X API" integration wrappers
# that don't match anything more specific, without drowning out real signal.
_GENERIC_MCP_FALLBACK = [
    "mcp server", "mcp-server", "model context protocol",
    "model-context-protocol",
]


def classify_agent(text: str) -> str:
    """Classify a single agent from a combined text blob of everything known
    about it (name, description, tags, keywords, topics, skill names/descriptions).
    Returns one of CATEGORIES. First-pass heuristic — expect to refine the
    keyword lists once real distributions come back from migrations/classify_agents.py.
    """
    if not text:
        return "other"

    lowered = text.lower()
    scores = {
        category: sum(1 for kw in keywords if kw in lowered)
        for category, keywords in _KEYWORDS.items()
    }

    best_category = max(scores, key=scores.get)
    if scores[best_category] > 0:
        return best_category

    if any(kw in lowered for kw in _GENERIC_MCP_FALLBACK):
        return "developer_tool"
    return "other"
