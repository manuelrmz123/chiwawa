"""
Adds known A2A launch partners and common agent subdomains to seed_domains.
Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING.
"""
from dotenv import load_dotenv
import os, psycopg2

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Official A2A launch partners (announced at Google Cloud Next 2025)
# plus subdomains where agent cards are commonly served
DOMAINS = [
    # Official launch partners missing from current seed list
    "salesforce.com",
    "sap.com",
    "servicenow.com",
    "workday.com",
    "atlassian.com",
    "box.com",
    "zendesk.com",
    "paypal.com",
    "mongodb.com",
    "datastax.com",
    "elastic.co",
    # Agent-specific subdomains of companies already in the list
    "agents.google.com",
    "api.anthropic.com",
    "api.openai.com",
    "api.cohere.com",
    "api.mistral.ai",
    "api.together.xyz",
    "api.groq.com",
    "api.fireworks.ai",
    # Agent-specific subdomains of launch partners
    "agent.salesforce.com",
    "agents.salesforce.com",
    "api.salesforce.com",
    "agent.servicenow.com",
    "api.sap.com",
    "developer.workday.com",
    "developer.box.com",
    "developer.zendesk.com",
    "developer.atlassian.com",
    # A2A-focused projects and frameworks
    "a2aprotocol.ai",
    "agent2agent.dev",
    "googleapis.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    # Other agent platforms likely to adopt early
    "agentprotocol.ai",
    "fixieai.com",
    "steamship.com",
    "beam.dev",
]

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

added = 0
skipped = 0
for domain in DOMAINS:
    cur.execute("""
        INSERT INTO seed_domains (domain, source, status, consecutive_fails)
        VALUES (%s, 'manual_a2a_partners', 'pending', 0)
        ON CONFLICT (domain) DO NOTHING
    """, (domain,))
    if cur.rowcount:
        added += 1
    else:
        skipped += 1

conn.commit()

cur.execute('SELECT COUNT(*) FROM seed_domains')
total = cur.fetchone()[0]
conn.close()

print(f"Added: {added}  |  Already existed: {skipped}  |  Total domains: {total}")
