CREATE TABLE relationship_states (
    player_id TEXT NOT NULL CHECK (length(player_id) BETWEEN 1 AND 64),
    npc_id TEXT NOT NULL CHECK (length(npc_id) BETWEEN 1 AND 64),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    stage TEXT NOT NULL CHECK (stage IN ('newcomer', 'acquaintance', 'friend', 'trusted_ally')),
    rule_version TEXT NOT NULL CHECK (length(rule_version) BETWEEN 1 AND 32),
    last_effective_utc_day TEXT CHECK (last_effective_utc_day IS NULL OR length(last_effective_utc_day) = 10),
    updated_at INTEGER NOT NULL CHECK (updated_at > 0),
    PRIMARY KEY (player_id, npc_id)
);

CREATE TABLE relationship_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE CHECK (length(event_id) = 36),
    player_id TEXT NOT NULL CHECK (length(player_id) BETWEEN 1 AND 64),
    npc_id TEXT NOT NULL CHECK (length(npc_id) BETWEEN 1 AND 64),
    request_id TEXT NOT NULL UNIQUE CHECK (length(request_id) = 36),
    request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint) = 64),
    trace_id TEXT NOT NULL CHECK (length(trace_id) = 36),
    conversation_id TEXT NOT NULL CHECK (length(conversation_id) = 36),
    category TEXT CHECK (category IS NULL OR category IN ('supportive', 'friendly', 'neutral', 'dismissive', 'hostile')),
    confidence INTEGER CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 100),
    rule_version TEXT NOT NULL CHECK (length(rule_version) BETWEEN 1 AND 32),
    reason_code TEXT NOT NULL CHECK (reason_code IN ('rule_supportive', 'rule_friendly', 'rule_neutral', 'rule_dismissive', 'rule_hostile', 'low_confidence', 'candidate_invalid', 'cooldown', 'score_floor', 'score_ceiling')),
    proposed_delta INTEGER NOT NULL CHECK (proposed_delta BETWEEN -2 AND 2),
    applied_delta INTEGER NOT NULL CHECK (applied_delta BETWEEN -2 AND 2),
    before_score INTEGER NOT NULL CHECK (before_score BETWEEN 0 AND 100),
    before_stage TEXT NOT NULL CHECK (before_stage IN ('newcomer', 'acquaintance', 'friend', 'trusted_ally')),
    after_score INTEGER NOT NULL CHECK (after_score BETWEEN 0 AND 100),
    after_stage TEXT NOT NULL CHECK (after_stage IN ('newcomer', 'acquaintance', 'friend', 'trusted_ally')),
    effective_utc_day TEXT CHECK (effective_utc_day IS NULL OR length(effective_utc_day) = 10),
    occurred_at INTEGER NOT NULL CHECK (occurred_at > 0),
    FOREIGN KEY (player_id, npc_id) REFERENCES relationship_states (player_id, npc_id)
);

CREATE INDEX idx_relationship_events_scope_occurred
    ON relationship_events (player_id, npc_id, event_sequence);
