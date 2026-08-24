"""Deterministically export JSON Schema from the Pydantic contract source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from cyber_town.contracts.v1 import ApiErrorV1, DialogueRequestV1, DialogueResponseV1

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIRECTORY = PROJECT_ROOT / "contracts" / "v1"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

SCHEMA_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("api-error-v1.schema.json", ApiErrorV1),
    ("dialogue-request-v1.schema.json", DialogueRequestV1),
    ("dialogue-response-v1.schema.json", DialogueResponseV1),
)


def render_schemas() -> dict[str, str]:
    """Return stable filenames and canonical UTF-8 JSON content."""

    rendered: dict[str, str] = {}
    for filename, model in SCHEMA_MODELS:
        schema = model.model_json_schema(mode="validation")
        schema["$id"] = f"https://cyber-town.local/schemas/v1/{filename}"
        schema["$schema"] = JSON_SCHEMA_DIALECT
        rendered[filename] = (
            json.dumps(
                schema,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return rendered


def schema_drift() -> list[str]:
    """List missing or stale derived schemas without modifying the filesystem."""

    rendered = render_schemas()
    drift: set[str] = set()
    for filename, expected in rendered.items():
        path = SCHEMA_DIRECTORY / filename
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            drift.add(filename)

    if SCHEMA_DIRECTORY.is_dir():
        actual = {path.name for path in SCHEMA_DIRECTORY.glob("*.schema.json")}
        drift.update(actual - rendered.keys())

    return sorted(drift)


def write_schemas() -> None:
    """Write all derived schemas to their versioned directory."""

    SCHEMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for filename, content in render_schemas().items():
        (SCHEMA_DIRECTORY / filename).write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    """Export schemas, or fail if committed schemas differ from their source."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report schema drift without writing files",
    )
    args = parser.parse_args()

    if args.check:
        drift = schema_drift()
        if drift:
            parser.exit(1, f"Schema drift detected: {', '.join(drift)}\n")
        return 0

    write_schemas()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
