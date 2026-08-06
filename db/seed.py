import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Seed list: AI companies, agent frameworks, known deployments
# These are real domains worth checking for /.well-known/agent.json
DOMAINS = [
    # AI labs and major players
    "anthropic.com",
    "openai.com",
    "google.com",
    "deepmind.com",
    "mistral.ai",
    "cohere.com",
    "ai21.com",
    "inflection.ai",
    "adept.ai",
    "stability.ai",
    "aleph-alpha.com",
    "huggingface.co",
    "replicate.com",
    "together.ai",
    "fireworks.ai",
    "groq.com",

    # Agent frameworks and platforms
    "langchain.com",
    "llamaindex.ai",
    "crewai.com",
    "agentops.ai",
    "e2b.dev",
    "superagent.sh",
    "fixie.ai",
    "dust.tt",
    "flowise.ai",
    "gptscript.ai",
    "mindsdb.com",
    "steamship.com",
    "relevanceai.com",

    # Developer platforms that host agents
    "replit.com",
    "val.town",
    "pipedream.com",
    "zapier.com",
    "make.com",
    "n8n.io",

    # MCP-related known projects
    "modelcontextprotocol.io",
    "mcp.so",
    "smithery.ai",

    # AI assistants and products
    "perplexity.ai",
    "you.com",
    "phind.com",
    "poe.com",
    "character.ai",
    "pi.ai",
    "claude.ai",

    # Vertical AI agents
    "harvey.ai",
    "casetext.com",
    "ironclad.ai",
    "donotpay.com",
    "klarna.com",
    "intercom.com",
    "drift.com",
    "forethought.ai",
    "corti.ai",
    "nabla.com",
    "hippocraticai.com",
    "abridge.com",
    "otter.ai",
    "fireflies.ai",
    "gong.io",
    "chorus.ai",
    "salesloft.com",
    "outreach.io",
    "apollo.io",
    "seamless.ai",

    # Coding agents
    "cursor.sh",
    "github.com",
    "sourcegraph.com",
    "codeium.com",
    "tabnine.com",
    "codium.ai",
    "sweep.dev",
    "continue.dev",
    "aider.chat",

    # Research and data agents
    "elicit.com",
    "consensus.app",
    "scite.ai",
    "semanticscholar.org",
    "connected-papers.com",

    # Automation and RPA
    "uipath.com",
    "automationanywhere.com",
    "workato.com",
    "tray.io",

    # AI infrastructure
    "modal.com",
    "banana.dev",
    "beam.cloud",
    "baseten.co",
    "cerebrium.ai",
    "lepton.ai",
    "runpod.io",

    # Agent-specific startups (likely early A2A adopters)
    "agentlabs.dev",
    "arcade.dev",
    "letta.ai",
    "autogen.microsoft.com",
    "agentverse.ai",
    "fetch.ai",
    "virtuals.io",

    # General developer tools that may expose agents
    "linear.app",
    "notion.so",
    "airtable.com",
    "retool.com",
    "airplane.dev",
    "windmill.dev",
]


def seed():
    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for domain in DOMAINS:
            try:
                cur.execute("""
                    INSERT INTO seed_domains (domain, source, status)
                    VALUES (%s, 'manual', 'pending')
                    ON CONFLICT (domain) DO NOTHING
                """, (domain,))
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"Error inserting {domain}: {e}")

    conn.close()
    print(f"Seeding complete: {inserted} inserted, {skipped} already existed.")


if __name__ == "__main__":
    seed()
