"""Read-only local reporting for metadata-only observability SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cyber_town.application.observability import TerminalOutcome, TraceErrorCode
from cyber_town.infrastructure.observability.sqlite_observability import (
    ObservabilityQuery,
    ObservabilityStorageError,
    SqliteObservabilityRepository,
)


def _uuid(value: str) -> UUID:
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("invalid UUID") from error
    if str(parsed) != value:
        raise argparse.ArgumentTypeError("invalid UUID")
    return parsed


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("timestamp must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise argparse.ArgumentTypeError("invalid timestamp") from error
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise argparse.ArgumentTypeError("timestamp must use UTC")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read bounded metadata-only observability summaries.",
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--trace-id", type=_uuid)
    parser.add_argument("--request-id", type=_uuid)
    parser.add_argument("--since-utc", type=_utc)
    parser.add_argument("--until-utc", type=_utc)
    parser.add_argument("--outcome", choices=tuple(outcome.value for outcome in TerminalOutcome))
    parser.add_argument("--error-code", choices=tuple(code.value for code in TraceErrorCode))
    parser.add_argument("--persona-version")
    parser.add_argument("--scope-tag")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--section", choices=("traces", "evaluations", "replay"), default="traces")
    parser.add_argument("--json", action="store_true")
    return parser


def _text_summary(row: dict[str, object]) -> str:
    return " ".join(
        (
            f"trace={row['trace_id']}",
            f"outcome={row['terminal_outcome']}",
            f"error={row['error_code']}",
            f"persona={row['persona_version']}",
            f"provider={row['provider_kind']}",
            f"retention={row['retention_status']}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
        database = arguments.database
        repository = SqliteObservabilityRepository(
            database_path=database,
            allowed_root=database.parent,
        )
        query = ObservabilityQuery(
            trace_id=arguments.trace_id,
            request_id=arguments.request_id,
            since_utc=arguments.since_utc,
            until_utc=arguments.until_utc,
            terminal_outcome=(
                None if arguments.outcome is None else TerminalOutcome(arguments.outcome)
            ),
            error_code=(
                None if arguments.error_code is None else TraceErrorCode(arguments.error_code)
            ),
            persona_version=arguments.persona_version,
            scope_tag=arguments.scope_tag,
            limit=arguments.limit,
        )
        trace_filters = (
            arguments.trace_id,
            arguments.request_id,
            arguments.since_utc,
            arguments.until_utc,
            arguments.outcome,
            arguments.error_code,
            arguments.persona_version,
            arguments.scope_tag,
        )
        if arguments.section != "traces" and any(value is not None for value in trace_filters):
            raise ValueError("Trace filters require the trace section")
        traces = repository.query_traces(query) if arguments.section == "traces" else ()
        evaluations = (
            repository.query_evaluations(limit=arguments.limit)
            if arguments.section == "evaluations"
            else ()
        )
        replay_index = (
            repository.query_replay_index(limit=arguments.limit)
            if arguments.section == "replay"
            else ()
        )
        retention = repository.retention_summary()
    except (ObservabilityStorageError, TypeError, ValueError, OSError):
        print("observability_report_unavailable", file=sys.stderr)
        return 1

    if arguments.json:
        section_payloads: dict[str, dict[str, object]] = {
            "traces": {"trace_count": len(traces), "traces": traces},
            "evaluations": {
                "evaluation_count": len(evaluations),
                "evaluations": evaluations,
            },
            "replay": {
                "replay_count": len(replay_index),
                "replay_index": replay_index,
            },
        }
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    **section_payloads[arguments.section],
                    "retention_summary": retention,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    elif arguments.section == "traces" and traces:
        for trace in traces:
            print(_text_summary(trace))
    elif arguments.section == "evaluations" and evaluations:
        for evaluation in evaluations:
            print(
                f"evaluation={evaluation['run_id']} passed={evaluation['passed_count']}/"
                f"{evaluation['case_count']} retention={evaluation['retention_status']}"
            )
    elif arguments.section == "replay" and replay_index:
        for replay in replay_index:
            print(
                f"replay={replay['replay_id']} mode={replay['execution_mode']} "
                f"retention={replay['retention_status']}"
            )
    else:
        print(f"no_{arguments.section}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
