CREATE TABLE trace_runs (
    trace_id TEXT PRIMARY KEY CHECK (length(trace_id) = 36),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    request_id TEXT CHECK (request_id IS NULL OR length(request_id) = 36),
    execution_id TEXT CHECK (execution_id IS NULL OR length(execution_id) = 36),
    attempt_kind TEXT NOT NULL CHECK (
        attempt_kind IN ('initial', 'retry', 'concurrent_waiter', 'cache_replay', 'validation_failure')
    ),
    player_scope_tag TEXT CHECK (player_scope_tag IS NULL OR length(player_scope_tag) = 64),
    npc_scope_tag TEXT CHECK (npc_scope_tag IS NULL OR length(npc_scope_tag) = 64),
    conversation_scope_tag TEXT CHECK (
        conversation_scope_tag IS NULL OR length(conversation_scope_tag) = 64
    ),
    persona_version TEXT CHECK (
        persona_version IS NULL OR length(persona_version) BETWEEN 1 AND 64
    ),
    provider_kind TEXT NOT NULL CHECK (
        provider_kind IN ('fake', 'deepseek', 'local-fallback', 'local-memory', 'disabled', 'unknown')
    ),
    record_status TEXT NOT NULL CHECK (record_status IN ('open', 'complete', 'partial')),
    terminal_outcome TEXT CHECK (
        terminal_outcome IS NULL OR terminal_outcome IN (
            'completed', 'degraded', 'rejected', 'failed', 'cancelled', 'orphaned',
            'replayed', 'conflict', 'abandoned_after_restart'
        )
    ),
    error_code TEXT NOT NULL CHECK (
        error_code IN (
            'none', 'validation_error', 'npc_not_found', 'conflict', 'provider_timeout',
            'provider_unavailable', 'provider_invalid_response', 'unsafe_content',
            'internal_error', 'observability_unavailable'
        )
    ),
    reason_code TEXT NOT NULL CHECK (
        reason_code IN (
            'none', 'completed', 'degraded_content_filter', 'degraded_no_history',
            'local_memory_command', 'cache_replay', 'shared_execution', 'cancelled',
            'orphaned', 'restart_recovery', 'not_reached'
        )
    ),
    idempotency_outcome TEXT NOT NULL CHECK (
        idempotency_outcome IN ('not_reached', 'new', 'inflight_shared', 'cache_replay', 'conflict')
    ),
    short_term_outcome TEXT NOT NULL CHECK (
        short_term_outcome IN ('not_reached', 'empty', 'selected', 'committed', 'aborted', 'failed')
    ),
    long_term_outcome TEXT NOT NULL CHECK (
        long_term_outcome IN (
            'not_reached', 'not_configured', 'empty', 'retrieved', 'command_completed', 'failed'
        )
    ),
    relationship_outcome TEXT NOT NULL CHECK (
        relationship_outcome IN ('not_reached', 'not_configured', 'applied', 'inert', 'failed')
    ),
    retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
    from_cache INTEGER NOT NULL CHECK (from_cache IN (0, 1)),
    provider_dispatch_count INTEGER NOT NULL CHECK (provider_dispatch_count IN (0, 1)),
    started_at_ms INTEGER NOT NULL CHECK (started_at_ms > 0),
    finished_at_ms INTEGER CHECK (finished_at_ms IS NULL OR finished_at_ms >= started_at_ms),
    total_latency_ms INTEGER NOT NULL CHECK (total_latency_ms >= 0),
    provider_wait_ms INTEGER NOT NULL CHECK (provider_wait_ms >= 0),
    provider_latency_ms INTEGER NOT NULL CHECK (provider_latency_ms >= 0),
    context_budget_units INTEGER NOT NULL CHECK (context_budget_units >= 0),
    selected_short_term_turns INTEGER NOT NULL CHECK (selected_short_term_turns >= 0),
    selected_long_term_facts INTEGER NOT NULL CHECK (selected_long_term_facts >= 0),
    input_chars INTEGER NOT NULL CHECK (input_chars >= 0),
    output_chars INTEGER NOT NULL CHECK (output_chars >= 0),
    prompt_tokens INTEGER NOT NULL CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL CHECK (
        total_tokens >= 0 AND total_tokens = prompt_tokens + completion_tokens
    ),
    cost_micro_usd INTEGER NOT NULL CHECK (cost_micro_usd = 0),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    marked_expired_at_ms INTEGER CHECK (
        marked_expired_at_ms IS NULL OR marked_expired_at_ms >= started_at_ms
    ),
    CHECK (
        (player_scope_tag IS NULL AND npc_scope_tag IS NULL AND conversation_scope_tag IS NULL)
        OR
        (player_scope_tag IS NOT NULL AND npc_scope_tag IS NOT NULL AND conversation_scope_tag IS NOT NULL)
    ),
    CHECK (
        (record_status = 'open' AND terminal_outcome IS NULL AND finished_at_ms IS NULL)
        OR
        (record_status IN ('complete', 'partial') AND terminal_outcome IS NOT NULL AND finished_at_ms IS NOT NULL)
    )
) STRICT;

CREATE INDEX idx_trace_runs_request ON trace_runs (request_id, started_at_ms DESC);
CREATE INDEX idx_trace_runs_execution ON trace_runs (execution_id, started_at_ms DESC);
CREATE INDEX idx_trace_runs_time_outcome
    ON trace_runs (started_at_ms DESC, terminal_outcome, error_code);
CREATE INDEX idx_trace_runs_persona ON trace_runs (persona_version, started_at_ms DESC);
CREATE INDEX idx_trace_runs_player_scope ON trace_runs (player_scope_tag, started_at_ms DESC);
CREATE INDEX idx_trace_runs_npc_scope ON trace_runs (npc_scope_tag, started_at_ms DESC);
CREATE INDEX idx_trace_runs_conversation_scope
    ON trace_runs (conversation_scope_tag, started_at_ms DESC);
CREATE INDEX idx_trace_runs_retention ON trace_runs (retention_status, finished_at_ms DESC);

CREATE TABLE trace_stage_events (
    trace_id TEXT NOT NULL REFERENCES trace_runs (trace_id),
    sequence INTEGER NOT NULL CHECK (sequence BETWEEN 1 AND 14),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    stage TEXT NOT NULL CHECK (
        stage IN (
            'http_received', 'request_validation', 'persona_resolution',
            'idempotency_resolution', 'scope_lock', 'short_term_selection',
            'long_term_retrieval', 'context_budget_selection', 'provider_queue',
            'provider_completion', 'relationship_evaluation', 'state_commit',
            'response_mapping', 'terminal'
        )
    ),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('started', 'completed', 'skipped', 'failed', 'cancelled', 'not_reached')
    ),
    reason_code TEXT NOT NULL CHECK (
        reason_code IN (
            'none', 'completed', 'degraded_content_filter', 'degraded_no_history',
            'local_memory_command', 'cache_replay', 'shared_execution', 'cancelled',
            'orphaned', 'restart_recovery', 'not_reached'
        )
    ),
    error_code TEXT NOT NULL CHECK (
        error_code IN (
            'none', 'validation_error', 'npc_not_found', 'conflict', 'provider_timeout',
            'provider_unavailable', 'provider_invalid_response', 'unsafe_content',
            'internal_error', 'observability_unavailable'
        )
    ),
    started_at_ms INTEGER NOT NULL CHECK (started_at_ms > 0),
    finished_at_ms INTEGER CHECK (finished_at_ms IS NULL OR finished_at_ms >= started_at_ms),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    PRIMARY KEY (trace_id, sequence),
    UNIQUE (trace_id, stage),
    CHECK (
        (stage = 'http_received' AND sequence = 1)
        OR (stage = 'request_validation' AND sequence = 2)
        OR (stage = 'persona_resolution' AND sequence = 3)
        OR (stage = 'idempotency_resolution' AND sequence = 4)
        OR (stage = 'scope_lock' AND sequence = 5)
        OR (stage = 'short_term_selection' AND sequence = 6)
        OR (stage = 'long_term_retrieval' AND sequence = 7)
        OR (stage = 'context_budget_selection' AND sequence = 8)
        OR (stage = 'provider_queue' AND sequence = 9)
        OR (stage = 'provider_completion' AND sequence = 10)
        OR (stage = 'relationship_evaluation' AND sequence = 11)
        OR (stage = 'state_commit' AND sequence = 12)
        OR (stage = 'response_mapping' AND sequence = 13)
        OR (stage = 'terminal' AND sequence = 14)
    )
) STRICT;

CREATE INDEX idx_trace_stage_events_stage_outcome
    ON trace_stage_events (stage, outcome, trace_id);
CREATE INDEX idx_trace_stage_events_retention
    ON trace_stage_events (retention_status, trace_id);

CREATE TABLE execution_links (
    trace_id TEXT PRIMARY KEY REFERENCES trace_runs (trace_id),
    execution_id TEXT NOT NULL CHECK (length(execution_id) = 36),
    link_kind TEXT NOT NULL CHECK (link_kind IN ('dispatch_owner', 'shared_waiter', 'local_execution')),
    provider_dispatch_count INTEGER NOT NULL CHECK (provider_dispatch_count IN (0, 1)),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    CHECK (
        (link_kind = 'dispatch_owner' AND provider_dispatch_count = 1)
        OR (link_kind IN ('shared_waiter', 'local_execution') AND provider_dispatch_count = 0)
    )
) STRICT;

CREATE UNIQUE INDEX idx_execution_links_one_dispatch_owner
    ON execution_links (execution_id) WHERE provider_dispatch_count = 1;
CREATE INDEX idx_execution_links_execution ON execution_links (execution_id, link_kind);
CREATE INDEX idx_execution_links_retention ON execution_links (retention_status, trace_id);

CREATE TABLE evaluation_runs (
    run_id TEXT PRIMARY KEY CHECK (length(run_id) = 36),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    evaluator_version TEXT NOT NULL CHECK (length(evaluator_version) BETWEEN 1 AND 64),
    fixture_version TEXT NOT NULL CHECK (length(fixture_version) BETWEEN 1 AND 64),
    started_at_ms INTEGER NOT NULL CHECK (started_at_ms > 0),
    finished_at_ms INTEGER NOT NULL CHECK (finished_at_ms >= started_at_ms),
    case_count INTEGER NOT NULL CHECK (case_count > 0),
    passed_count INTEGER NOT NULL CHECK (passed_count BETWEEN 0 AND case_count),
    failed_count INTEGER NOT NULL CHECK (
        failed_count BETWEEN 0 AND case_count AND passed_count + failed_count = case_count
    ),
    trace_completeness_ppm INTEGER NOT NULL CHECK (trace_completeness_ppm BETWEEN 0 AND 1000000),
    stage_consistency_ppm INTEGER NOT NULL CHECK (stage_consistency_ppm BETWEEN 0 AND 1000000),
    scope_leak_count INTEGER NOT NULL CHECK (scope_leak_count >= 0),
    forbidden_content_hit_count INTEGER NOT NULL CHECK (forbidden_content_hit_count >= 0),
    provider_attribution_error_count INTEGER NOT NULL CHECK (provider_attribution_error_count >= 0),
    nonzero_cost_case_count INTEGER NOT NULL CHECK (nonzero_cost_case_count >= 0),
    canonical_digest TEXT NOT NULL CHECK (length(canonical_digest) = 64),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    marked_expired_at_ms INTEGER CHECK (
        marked_expired_at_ms IS NULL OR marked_expired_at_ms >= started_at_ms
    )
) STRICT;

CREATE INDEX idx_evaluation_runs_time ON evaluation_runs (started_at_ms DESC, run_id);
CREATE INDEX idx_evaluation_runs_retention
    ON evaluation_runs (retention_status, finished_at_ms DESC);

CREATE TABLE evaluation_cases (
    run_id TEXT NOT NULL REFERENCES evaluation_runs (run_id),
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    case_id TEXT NOT NULL CHECK (length(case_id) BETWEEN 1 AND 64),
    dimension TEXT NOT NULL CHECK (
        dimension IN (
            'persona_identity', 'reply_outcome', 'short_term_isolation',
            'persistent_isolation', 'adversarial_input', 'idempotency_concurrency',
            'cancellation_late_result', 'recorder_failure'
        )
    ),
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    failure_code TEXT NOT NULL CHECK (
        failure_code IN (
            'none', 'persona_mismatch', 'metadata_mismatch', 'trace_incomplete',
            'stage_inconsistent', 'scope_leak', 'forbidden_content',
            'provider_attribution', 'cost_nonzero', 'business_semantics_changed'
        )
    ),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    PRIMARY KEY (run_id, sequence),
    UNIQUE (run_id, case_id),
    CHECK ((passed = 1 AND failure_code = 'none') OR (passed = 0 AND failure_code <> 'none'))
) STRICT;

CREATE INDEX idx_evaluation_cases_dimension
    ON evaluation_cases (dimension, passed, run_id);
CREATE INDEX idx_evaluation_cases_retention
    ON evaluation_cases (retention_status, run_id);

CREATE TABLE replay_index (
    replay_id TEXT PRIMARY KEY CHECK (length(replay_id) = 36),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    trace_id TEXT REFERENCES trace_runs (trace_id),
    request_id TEXT CHECK (request_id IS NULL OR length(request_id) = 36),
    execution_id TEXT CHECK (execution_id IS NULL OR length(execution_id) = 36),
    fixture_version TEXT CHECK (
        fixture_version IS NULL OR length(fixture_version) BETWEEN 1 AND 64
    ),
    case_id TEXT CHECK (case_id IS NULL OR length(case_id) BETWEEN 1 AND 64),
    evaluator_version TEXT NOT NULL CHECK (length(evaluator_version) BETWEEN 1 AND 64),
    persona_version TEXT CHECK (
        persona_version IS NULL OR length(persona_version) BETWEEN 1 AND 64
    ),
    terminal_outcome TEXT CHECK (
        terminal_outcome IS NULL OR terminal_outcome IN (
            'completed', 'degraded', 'rejected', 'failed', 'cancelled', 'orphaned',
            'replayed', 'conflict', 'abandoned_after_restart'
        )
    ),
    digest TEXT NOT NULL CHECK (length(digest) = 64),
    execution_mode TEXT NOT NULL CHECK (
        execution_mode IN ('metadata_only_not_executable', 'synthetic_fixture_executable')
    ),
    created_at_ms INTEGER NOT NULL CHECK (created_at_ms > 0),
    retention_status TEXT NOT NULL DEFAULT 'active' CHECK (retention_status IN ('active', 'expired')),
    marked_expired_at_ms INTEGER CHECK (
        marked_expired_at_ms IS NULL OR marked_expired_at_ms >= created_at_ms
    ),
    CHECK (
        (
            execution_mode = 'metadata_only_not_executable'
            AND trace_id IS NOT NULL
            AND fixture_version IS NULL
            AND case_id IS NULL
        )
        OR
        (
            execution_mode = 'synthetic_fixture_executable'
            AND trace_id IS NULL
            AND request_id IS NULL
            AND execution_id IS NULL
            AND fixture_version IS NOT NULL
            AND case_id IS NOT NULL
        )
    )
) STRICT;

CREATE INDEX idx_replay_index_trace ON replay_index (trace_id, created_at_ms DESC);
CREATE INDEX idx_replay_index_fixture
    ON replay_index (fixture_version, case_id, created_at_ms DESC);
CREATE INDEX idx_replay_index_retention
    ON replay_index (retention_status, created_at_ms DESC);

PRAGMA user_version = 1;
