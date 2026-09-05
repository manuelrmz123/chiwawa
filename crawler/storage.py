import hashlib
import json
import psycopg2
from datetime import datetime, timezone


def get_connection(db_url: str):
    return psycopg2.connect(db_url)


def compute_hash(card: dict) -> str:
    normalized = json.dumps(card, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


def determine_status(consecutive_fails: int, dns_resolves: bool, http_status: int | None, last_seen_at: datetime | None) -> str:
    if http_status == 410:
        return "gone"
    if not dns_resolves:
        return "unreachable"
    if consecutive_fails == 0:
        return "active"
    if consecutive_fails <= 3:
        return "degraded"
    if last_seen_at:
        days_since = (datetime.now(timezone.utc) - last_seen_at.replace(tzinfo=timezone.utc)).days
        if days_since >= 90:
            return "archived"
        if days_since >= 7:
            return "unresponsive"
    return "degraded"


def get_pending_domains(conn, limit: int = 100) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, domain FROM seed_domains
            WHERE next_crawl_at IS NULL OR next_crawl_at <= now()
            ORDER BY next_crawl_at ASC NULLS FIRST
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
    return [{"id": str(r[0]), "domain": r[1]} for r in rows]


def _provider_fields(card: dict) -> tuple[str | None, str | None]:
    """A2A spec allows provider to be a string or an object."""
    provider = card.get("provider")
    if isinstance(provider, str):
        return provider, None
    if isinstance(provider, dict):
        return provider.get("organization"), provider.get("url")
    return None, None


def upsert_agent(conn, result: dict) -> str | None:
    if not result["success"] or not result["card"]:
        return None

    card = result["card"]
    card_hash = compute_hash(card)

    with conn.cursor() as cur:
        cur.execute("SELECT id, card_hash FROM agents WHERE card_url = %s", (result["url"],))
        existing = cur.fetchone()

        if existing:
            agent_id, old_hash = str(existing[0]), existing[1]

            if old_hash != card_hash:
                cur.execute("""
                    INSERT INTO agent_card_history (agent_id, changed_at, previous_hash, new_hash, previous_card, new_card)
                    SELECT id, now(), %s, %s,
                           (SELECT raw_card FROM agents WHERE id = %s),
                           %s::jsonb
                    FROM agents WHERE id = %s
                """, (old_hash, card_hash, agent_id, json.dumps(card), agent_id))

            cur.execute("""
                UPDATE agents SET
                    name = %s, description = %s, base_url = %s,
                    provider_name = %s, provider_url = %s, version = %s,
                    raw_card = %s::jsonb, card_hash = %s,
                    status = %s, consecutive_fails = 0,
                    last_http_status = %s, last_response_time_ms = %s,
                    dns_resolves = %s, ssl_valid = %s,
                    last_seen_at = now(), last_checked_at = now()
                WHERE id = %s
            """, (
                card.get("name"), card.get("description"), card.get("url"),
                *_provider_fields(card),
                card.get("version"),
                json.dumps(card), card_hash,
                "active", result["status_code"], result["response_time_ms"],
                result["dns_resolves"], result["ssl_valid"],
                agent_id
            ))
        else:
            cur.execute("""
                INSERT INTO agents (
                    type, name, description, base_url, card_url,
                    provider_name, provider_url, version,
                    raw_card, card_hash, status, consecutive_fails,
                    last_http_status, last_response_time_ms,
                    dns_resolves, ssl_valid,
                    last_seen_at, last_checked_at, first_seen_at
                ) VALUES (
                    'a2a', %s, %s, %s, %s,
                    %s, %s, %s,
                    %s::jsonb, %s, 'active', 0,
                    %s, %s,
                    %s, %s,
                    now(), now(), now()
                ) RETURNING id
            """, (
                card.get("name"), card.get("description"), card.get("url"), result["url"],
                *_provider_fields(card),
                card.get("version"),
                json.dumps(card), card_hash,
                result["status_code"], result["response_time_ms"],
                result["dns_resolves"], result["ssl_valid"]
            ))
            agent_id = str(cur.fetchone()[0])

            skills = card.get("skills", [])
            auth = card.get("authentication")
            schemes = auth.get("schemes", []) if isinstance(auth, dict) else []
            input_modes  = card.get("defaultInputModes", [])
            output_modes = card.get("defaultOutputModes", [])
            _upsert_skills(cur, agent_id, skills if isinstance(skills, list) else [])
            _upsert_auth_schemes(cur, agent_id, schemes)
            _upsert_io_modes(cur, agent_id,
                             input_modes  if isinstance(input_modes,  list) else [],
                             output_modes if isinstance(output_modes, list) else [])

    conn.commit()
    return agent_id


def _upsert_skills(cur, agent_id: str, skills: list):
    cur.execute("DELETE FROM agent_skills WHERE agent_id = %s", (agent_id,))
    for skill in skills:
        cur.execute("""
            INSERT INTO agent_skills (agent_id, skill_id, name, description, tags, examples)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            agent_id,
            skill.get("id"),
            skill.get("name"),
            skill.get("description"),
            skill.get("tags", []),
            skill.get("examples", [])
        ))


def _upsert_auth_schemes(cur, agent_id: str, schemes: list):
    cur.execute("DELETE FROM agent_auth_schemes WHERE agent_id = %s", (agent_id,))
    for scheme in schemes:
        cur.execute("INSERT INTO agent_auth_schemes (agent_id, scheme) VALUES (%s, %s)", (agent_id, scheme))


def _upsert_io_modes(cur, agent_id: str, input_modes: list, output_modes: list):
    cur.execute("DELETE FROM agent_io_modes WHERE agent_id = %s", (agent_id,))
    for mode in input_modes:
        cur.execute("INSERT INTO agent_io_modes (agent_id, direction, mime_type) VALUES (%s, 'input', %s)", (agent_id, mode))
    for mode in output_modes:
        cur.execute("INSERT INTO agent_io_modes (agent_id, direction, mime_type) VALUES (%s, 'output', %s)", (agent_id, mode))


def log_crawl(conn, result: dict, agent_id: str | None, card_hash: str | None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO crawl_log (agent_id, domain, checked_at, http_status, response_time_ms, success, error_message, card_hash)
            VALUES (%s, %s, now(), %s, %s, %s, %s, %s)
        """, (
            agent_id,
            result["domain"],
            result["status_code"],
            result["response_time_ms"],
            result["success"],
            result.get("error"),
            card_hash
        ))
    conn.commit()


def update_seed_domain(conn, domain_id: str, success: bool, consecutive_fails: int):
    from datetime import timedelta

    if success:
        next_crawl = "now() + interval '6 hours'"
        fails = 0
    elif consecutive_fails <= 3:
        next_crawl = "now() + interval '24 hours'"
        fails = consecutive_fails + 1
    elif consecutive_fails <= 10:
        next_crawl = "now() + interval '7 days'"
        fails = consecutive_fails + 1
    else:
        next_crawl = "now() + interval '30 days'"
        fails = consecutive_fails + 1

    with conn.cursor() as cur:
        cur.execute(f"""
            UPDATE seed_domains
            SET last_crawled_at = now(),
                next_crawl_at = {next_crawl},
                consecutive_fails = %s,
                status = CASE WHEN %s THEN 'active' ELSE status END
            WHERE id = %s
        """, (fails, success, domain_id))
    conn.commit()
