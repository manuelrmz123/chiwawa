-- Chiwawa — Unified AI Agent Registry
-- Database schema

-- seed_domains: the crawl queue
CREATE TABLE IF NOT EXISTS seed_domains (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    domain            text NOT NULL UNIQUE,
    source            text NOT NULL DEFAULT 'manual',
    status            text NOT NULL DEFAULT 'pending',
    last_crawled_at   timestamp,
    next_crawl_at     timestamp,
    consecutive_fails integer NOT NULL DEFAULT 0
);

-- agents: one row per discovered agent
CREATE TABLE IF NOT EXISTS agents (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type                  text NOT NULL,
    name                  text,
    description           text,
    base_url              text,
    card_url              text,
    provider_name         text,
    provider_url          text,
    version               text,
    raw_card              jsonb,
    card_hash             text,
    did                   text UNIQUE,

    -- Health & status
    status                text NOT NULL DEFAULT 'active',
    consecutive_fails     integer NOT NULL DEFAULT 0,
    last_http_status      integer,
    last_response_time_ms integer,
    dns_resolves          boolean,
    ssl_valid             boolean,
    last_seen_at          timestamp,
    last_checked_at       timestamp,
    last_status_change_at timestamp,
    first_seen_at         timestamp NOT NULL DEFAULT now(),

    -- Crawl scheduling
    next_crawl_at         timestamp,
    crawl_priority        integer NOT NULL DEFAULT 5,

    CONSTRAINT agents_type_check CHECK (type IN ('a2a', 'mcp_live', 'mcp_package')),
    CONSTRAINT agents_status_check CHECK (status IN ('active', 'degraded', 'unresponsive', 'unreachable', 'gone', 'archived'))
);

-- agent_skills: normalized from A2A skills array
CREATE TABLE IF NOT EXISTS agent_skills (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    skill_id    text,
    name        text,
    description text,
    tags        text[],
    examples    text[]
);

-- agent_auth_schemes: authentication methods the agent requires
CREATE TABLE IF NOT EXISTS agent_auth_schemes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    scheme      text NOT NULL
);

-- agent_io_modes: input and output MIME types
CREATE TABLE IF NOT EXISTS agent_io_modes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    direction   text NOT NULL,
    mime_type   text NOT NULL,

    CONSTRAINT agent_io_modes_direction_check CHECK (direction IN ('input', 'output'))
);

-- crawl_log: every check ever made, never deleted
CREATE TABLE IF NOT EXISTS crawl_log (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id          uuid REFERENCES agents(id) ON DELETE SET NULL,
    domain            text NOT NULL,
    checked_at        timestamp NOT NULL DEFAULT now(),
    http_status       integer,
    response_time_ms  integer,
    success           boolean NOT NULL,
    error_message     text,
    card_hash         text
);

-- agent_card_history: written only when a card changes
CREATE TABLE IF NOT EXISTS agent_card_history (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    changed_at      timestamp NOT NULL DEFAULT now(),
    previous_hash   text,
    new_hash        text,
    previous_card   jsonb,
    new_card        jsonb
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_type ON agents(type);
CREATE INDEX IF NOT EXISTS idx_agents_next_crawl ON agents(next_crawl_at);
CREATE INDEX IF NOT EXISTS idx_crawl_log_agent_id ON crawl_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_crawl_log_checked_at ON crawl_log(checked_at);
CREATE INDEX IF NOT EXISTS idx_seed_domains_next_crawl ON seed_domains(next_crawl_at);
CREATE INDEX IF NOT EXISTS idx_seed_domains_status ON seed_domains(status);
