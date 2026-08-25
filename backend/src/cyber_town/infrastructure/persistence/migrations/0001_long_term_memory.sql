CREATE TABLE long_term_memories (
    memory_id TEXT PRIMARY KEY CHECK (length(memory_id) = 36),
    player_id TEXT NOT NULL CHECK (length(player_id) BETWEEN 1 AND 64),
    npc_id TEXT NOT NULL CHECK (length(npc_id) BETWEEN 1 AND 64),
    memory_type TEXT NOT NULL CHECK (memory_type IN ('profile', 'preference')),
    fact_key TEXT NOT NULL CHECK (
        fact_key IN (
            'game_alias',
            'preferred_language',
            'reply_style',
            'favorite_cyber_town_topic'
        )
    ),
    fact_value TEXT,
    source_conversation_id TEXT NOT NULL CHECK (length(source_conversation_id) = 36),
    source_request_id TEXT NOT NULL CHECK (length(source_request_id) = 36),
    source_trace_id TEXT NOT NULL CHECK (length(source_trace_id) = 36),
    importance INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 5),
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 1000),
    created_at INTEGER NOT NULL CHECK (created_at > 0),
    updated_at INTEGER NOT NULL CHECK (updated_at >= created_at),
    expires_at INTEGER CHECK (expires_at IS NULL OR expires_at > created_at),
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'forgotten', 'expired')),
    CHECK (
        (status IN ('active', 'superseded') AND fact_value IS NOT NULL)
        OR (status IN ('forgotten', 'expired') AND fact_value IS NULL)
    ),
    UNIQUE (player_id, npc_id, memory_type, fact_key)
);

CREATE INDEX idx_long_term_memories_scope_status_expiry
    ON long_term_memories (player_id, npc_id, status, expires_at);

CREATE INDEX idx_long_term_memories_scope_fact
    ON long_term_memories (player_id, npc_id, fact_key);

CREATE INDEX idx_long_term_memories_updated
    ON long_term_memories (updated_at, memory_id);

CREATE TABLE memory_operations (
    request_id TEXT PRIMARY KEY CHECK (length(request_id) = 36),
    player_id TEXT NOT NULL CHECK (length(player_id) BETWEEN 1 AND 64),
    npc_id TEXT NOT NULL CHECK (length(npc_id) BETWEEN 1 AND 64),
    request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint) = 64),
    operation_type TEXT NOT NULL CHECK (operation_type IN ('remember', 'forget')),
    memory_id TEXT REFERENCES long_term_memories (memory_id),
    created_at INTEGER NOT NULL CHECK (created_at > 0)
);

CREATE TABLE memory_events (
    event_id TEXT PRIMARY KEY CHECK (length(event_id) = 36),
    memory_id TEXT NOT NULL REFERENCES long_term_memories (memory_id),
    request_id TEXT NOT NULL CHECK (length(request_id) = 36),
    event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'forgotten', 'expired')),
    created_at INTEGER NOT NULL CHECK (created_at > 0)
);
