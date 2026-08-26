from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.observability_report import main

from cyber_town.application.observability_evaluation import (
    build_baseline_observations,
    evaluate_observability,
    load_evaluation_fixture,
)
from cyber_town.infrastructure.observability.sqlite_observability import (
    ObservabilityQuery,
    ReplayIndexEntry,
)
from test_sqlite_observability import (
    FIXTURE_PATH,
    NOW,
    SYNTHETIC_KEY,
    _repository,
    _stages,
    _trace,
)


def test_cli_json_and_text_are_read_only_and_metadata_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))
    before = hashlib.sha256(repository.database_path.read_bytes()).hexdigest()

    assert main(["--database", str(repository.database_path), "--json", "--limit", "1"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["trace_count"] == 1
    assert payload["traces"][0]["trace_id"] == str(trace.trace_id)

    assert (
        main(["--database", str(repository.database_path), "--trace-id", str(trace.trace_id)]) == 0
    )
    captured = capsys.readouterr()
    assert f"trace={trace.trace_id}" in captured.out
    assert "outcome=completed" in captured.out
    assert hashlib.sha256(repository.database_path.read_bytes()).hexdigest() == before


def test_cli_filters_and_retention_summary_are_bounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))

    arguments = [
        "--database",
        str(repository.database_path),
        "--json",
        "--request-id",
        str(trace.request_id),
        "--outcome",
        "completed",
        "--error-code",
        "none",
        "--persona-version",
        "nia-v1",
        "--scope-tag",
        trace.scope_tags.player_scope_tag if trace.scope_tags is not None else "",
        "--since-utc",
        "2026-08-26T00:00:00Z",
        "--until-utc",
        "2026-08-27T00:00:00Z",
        "--limit",
        "10",
    ]
    assert main(arguments) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["trace_count"] == 1
    assert set(payload["retention_summary"]) == {
        "active_evaluation_count",
        "active_replay_count",
        "active_trace_count",
        "expired_evaluation_count",
        "expired_replay_count",
        "expired_trace_count",
    }


def test_cli_missing_or_corrupt_database_fails_closed_without_echoing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.sqlite3"
    assert main(["--database", str(missing), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "observability_report_unavailable"
    assert not missing.exists()

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"synthetic-corrupt-database")
    assert main(["--database", str(corrupt), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "observability_report_unavailable"
    assert str(corrupt) not in captured.err


def test_cli_parser_does_not_offer_sql_export_or_payload_options() -> None:
    query_fields = ObservabilityQuery.__dataclass_fields__
    assert "sql" not in query_fields
    assert "message" not in query_fields
    assert "reply" not in query_fields
    assert "export" not in query_fields


def test_cli_queries_evaluation_and_replay_summaries_without_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = _repository(tmp_path)
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    report = evaluate_observability(
        fixture,
        build_baseline_observations(fixture),
        SYNTHETIC_KEY,
    )
    run_id = uuid4()
    repository.save_evaluation(
        run_id=run_id,
        report=report,
        started_at_utc=NOW,
        finished_at_utc=NOW + timedelta(seconds=1),
    )
    trace = _trace()
    repository.save_trace(trace, _stages(trace))
    replay_id = uuid4()
    repository.save_replay_index(
        ReplayIndexEntry.metadata_only(
            replay_id=replay_id,
            trace=trace,
            digest="3" * 64,
            created_at_utc=NOW,
        )
    )
    before = hashlib.sha256(repository.database_path.read_bytes()).hexdigest()

    assert (
        main(
            [
                "--database",
                str(repository.database_path),
                "--section",
                "evaluations",
                "--json",
            ]
        )
        == 0
    )
    evaluation_payload = json.loads(capsys.readouterr().out)
    assert evaluation_payload["evaluation_count"] == 1
    assert evaluation_payload["evaluations"][0]["run_id"] == str(run_id)

    assert (
        main(
            [
                "--database",
                str(repository.database_path),
                "--section",
                "replay",
                "--json",
            ]
        )
        == 0
    )
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["replay_count"] == 1
    assert replay_payload["replay_index"][0]["replay_id"] == str(replay_id)
    assert replay_payload["replay_index"][0]["execution_mode"] == ("metadata_only_not_executable")
    assert hashlib.sha256(repository.database_path.read_bytes()).hexdigest() == before
