"""Offline quality, ignore-policy, and sensitive-information checks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import IO

from dotenv.parser import parse_stream
from pathspec import GitIgnoreSpec
from yaml import YAMLError, compose, safe_load
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

PROJECT_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_IGNORED_PATHS: tuple[str, ...] = (
    ".env",
    ".env.local",
    ".venv/pyvenv.cfg",
    ".tools/python/runtime.exe",
    ".cache/uv/archive",
    "data/runtime.db",
    "data/runtime.sqlite3",
    "data/qdrant/index",
    "logs/dialogue.jsonl",
    "artifacts/output.json",
    "reports/coverage.xml",
    ".godot/imported/resource",
)
EXPECTED_VISIBLE_PATHS: tuple[str, ...] = (
    ".env.example",
    ".gitignore",
    "contracts/v1/dialogue-request-v1.schema.json",
)

ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>.*)$",
    flags=re.IGNORECASE,
)
MAPPING_CREDENTIAL_KEY_PATTERN = re.compile(
    r"(?:^\s*(?:-\s*)?|[{,]\s*)[\"']?(?P<name>[A-Z_][A-Z0-9_]*)[\"']?\s*:",
    flags=re.IGNORECASE,
)
CREDENTIAL_NAME_SUFFIXES: tuple[str, ...] = (
    "API_KEY",
    "DATABASE_URL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "SECRET_ACCESS_KEY",
    "SECRET_KEY",
    "TOKEN",
)
TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {
        "changeme",
        "dummy",
        "example",
        "placeholder",
        "synthetic",
        "your-token-here",
        "your_token_here",
    }
)
MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
MAX_STRUCTURED_DEPTH = 100
BINARY_MAGIC_PREFIXES: tuple[bytes, ...] = (
    b"\x00\x00\x01\x00",
    b"\x00\x01\x00\x00",
    b"\x1aE\xdf\xa3",
    b"\x1f\x8b",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"%PDF-",
    b"GIF87a",
    b"GIF89a",
    b"ID3",
    b"OggS",
    b"OTTO",
    b"PK\x03\x04",
    b"RIFF",
    b"wOFF",
    b"wOF2",
)


class QualityCheckError(RuntimeError):
    """A quality check could not run or reported a policy violation."""


class DuplicateStructuredKeyError(ValueError):
    """A structured config contains a duplicate key and cannot be scanned safely."""


@dataclass(frozen=True, slots=True)
class SensitiveFinding:
    """A secret-like match that never stores or renders the matched value."""

    path: str
    line: int
    rule: str

    def safe_description(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}"


@dataclass(frozen=True, slots=True)
class GitIndexEntry:
    """A stage-zero Git index entry with its content object identifier."""

    path: str
    mode: str
    object_id: str


def quality_commands(python: str | None = None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return the offline command sequence used by local development and CI."""

    interpreter = python or sys.executable
    return (
        ("lock", ("uv", "lock", "--check")),
        ("ruff", (interpreter, "-m", "ruff", "check", "backend/src", "backend/tests", "scripts")),
        ("mypy", (interpreter, "-m", "mypy", "backend/src", "backend/tests", "scripts")),
        ("schema", (interpreter, "-m", "cyber_town.contracts.export", "--check")),
        ("pytest", (interpreter, "-m", "pytest")),
    )


def _repository_ignore_spec(root: Path) -> GitIgnoreSpec:
    try:
        lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise QualityCheckError("repository .gitignore could not be read") from error
    return GitIgnoreSpec.from_lines(lines)


def _git_index_ignore_spec(root: Path) -> GitIgnoreSpec | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "show", ":.gitignore"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        lines = completed.stdout.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise QualityCheckError("index .gitignore could not be read") from error
    return GitIgnoreSpec.from_lines(lines)


def _ignore_contract_violations(ignore_spec: GitIgnoreSpec, label: str) -> list[str]:
    prefix = f"{label} " if label else ""
    violations = [
        f"{prefix}required ignored path is visible: {path}"
        for path in EXPECTED_IGNORED_PATHS
        if not ignore_spec.match_file(path)
    ]
    violations.extend(
        f"{prefix}required visible path is ignored: {path}"
        for path in EXPECTED_VISIBLE_PATHS
        if ignore_spec.match_file(path)
    )
    return violations


def find_ignore_violations(root: Path) -> list[str]:
    """Verify runtime artifacts are ignored while public templates remain visible."""

    worktree_spec = _repository_ignore_spec(root)
    violations = _ignore_contract_violations(worktree_spec, "")
    index_spec = _git_index_ignore_spec(root)
    if index_spec is None:
        violations.append("index .gitignore is missing")
    else:
        violations.extend(_ignore_contract_violations(index_spec, "index"))
        violations.extend(
            f"index ignored path is tracked: {path}"
            for path in _git_tracked_files(root)
            if index_spec.match_file(path)
        )
    violations.extend(
        f"ignored path is tracked: {path}" for path in _git_ignored_tracked_files(root)
    )
    return sorted(violations)


def _git_tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualityCheckError("git ls-files could not enumerate tracked files")
    return sorted(
        os.fsdecode(raw_path).replace("\\", "/")
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )


def _git_ignored_tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--ignored",
            "--exclude-per-directory=.gitignore",
            "-z",
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualityCheckError("git ls-files could not verify tracked ignore violations")
    return sorted(
        os.fsdecode(raw_path).replace("\\", "/")
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return not normalized or normalized in PLACEHOLDER_VALUES


def _is_credential_name(name: str) -> bool:
    normalized = name.upper()
    return any(normalized.endswith(suffix) for suffix in CREDENTIAL_NAME_SUFFIXES)


def _is_recognized_binary(prefix: bytes) -> bool:
    return any(prefix.startswith(signature) for signature in BINARY_MAGIC_PREFIXES) or (
        len(prefix) >= 8 and prefix[4:8] == b"ftyp"
    )


def _scan_text_lines(lines: Iterable[str], relative: str) -> set[SensitiveFinding]:
    findings: set[SensitiveFinding] = set()
    suffix = Path(relative).suffix.lower()
    has_semantic_assignment_parser = _is_dotenv_path(relative) or suffix in {
        ".json",
        ".toml",
        ".yaml",
        ".yml",
    }
    for line_number, line in enumerate(lines, start=1):
        if not has_semantic_assignment_parser:
            for assignment in ENV_ASSIGNMENT_PATTERN.finditer(line):
                if _is_credential_name(assignment.group("name")) and not _is_placeholder(
                    assignment.group("value")
                ):
                    findings.add(SensitiveFinding(relative, line_number, "credential_assignment"))

        if suffix == ".jsonc":
            for assignment in MAPPING_CREDENTIAL_KEY_PATTERN.finditer(line):
                if _is_credential_name(assignment.group("name")):
                    findings.add(SensitiveFinding(relative, line_number, "credential_assignment"))

        for rule, pattern in TOKEN_PATTERNS:
            if pattern.search(line):
                findings.add(SensitiveFinding(relative, line_number, rule))
    return findings


def _is_dotenv_path(relative: str) -> bool:
    name = Path(relative).name.lower()
    return name == ".env" or ".env." in name or name.endswith(".env")


def _scan_dotenv(text: str, relative: str) -> set[SensitiveFinding]:
    findings: set[SensitiveFinding] = set()
    for binding in parse_stream(StringIO(text)):
        if binding.error:
            findings.add(SensitiveFinding(relative, binding.original.line, "scan_error"))
        elif (
            binding.key is not None
            and _is_credential_name(binding.key)
            and binding.value is not None
            and not _is_placeholder(binding.value)
        ):
            findings.add(SensitiveFinding(relative, binding.original.line, "credential_assignment"))
    return findings


def _scan_structured_value(
    value: object,
    relative: str,
    *,
    ancestors: set[int] | None = None,
    depth: int = 0,
) -> set[SensitiveFinding]:
    findings: set[SensitiveFinding] = set()
    if depth > MAX_STRUCTURED_DEPTH:
        return {SensitiveFinding(relative, 0, "scan_error")}
    active_ancestors = ancestors if ancestors is not None else set()
    is_container = isinstance(value, (dict, list))
    object_identity = id(value)
    if is_container and object_identity in active_ancestors:
        return {SensitiveFinding(relative, 0, "scan_error")}
    if is_container:
        active_ancestors.add(object_identity)

    if isinstance(value, dict):
        for key, nested in value.items():
            if (
                isinstance(key, str)
                and _is_credential_name(key)
                and nested is not None
                and (not isinstance(nested, str) or not _is_placeholder(nested))
            ):
                findings.add(SensitiveFinding(relative, 0, "credential_assignment"))
            findings.update(
                _scan_structured_value(
                    nested,
                    relative,
                    ancestors=active_ancestors,
                    depth=depth + 1,
                )
            )
    elif isinstance(value, list):
        for nested in value:
            findings.update(
                _scan_structured_value(
                    nested,
                    relative,
                    ancestors=active_ancestors,
                    depth=depth + 1,
                )
            )
    if is_container:
        active_ancestors.remove(object_identity)
    return findings


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateStructuredKeyError
        result[key] = value
    return result


def _yaml_structure_is_unsafe(
    node: Node,
    *,
    ancestors: set[int] | None = None,
    depth: int = 0,
) -> bool:
    if depth > MAX_STRUCTURED_DEPTH:
        return True
    active_ancestors = ancestors if ancestors is not None else set()
    node_identity = id(node)
    if node_identity in active_ancestors:
        return True
    active_ancestors.add(node_identity)
    unsafe = False
    if isinstance(node, MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                key_identity = (key_node.tag, key_node.value)
                if key_identity in seen:
                    unsafe = True
                    break
                seen.add(key_identity)
            if _yaml_structure_is_unsafe(
                key_node,
                ancestors=active_ancestors,
                depth=depth + 1,
            ) or _yaml_structure_is_unsafe(
                value_node,
                ancestors=active_ancestors,
                depth=depth + 1,
            ):
                unsafe = True
                break
    elif isinstance(node, SequenceNode):
        unsafe = any(
            _yaml_structure_is_unsafe(
                child,
                ancestors=active_ancestors,
                depth=depth + 1,
            )
            for child in node.value
        )
    active_ancestors.remove(node_identity)
    return unsafe


def _scan_content(
    content: bytes,
    relative: str,
    *,
    recognized_binary: bool,
) -> set[SensitiveFinding]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        if not recognized_binary:
            return {SensitiveFinding(relative, 0, "scan_error")}
        text = content.decode("utf-8-sig", errors="ignore")
    findings = _scan_text_lines(text.splitlines(keepends=True), relative)
    if _is_dotenv_path(relative):
        findings.update(_scan_dotenv(text, relative))
    suffix = Path(relative).suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(text, object_pairs_hook=_unique_json_object)
        except (json.JSONDecodeError, DuplicateStructuredKeyError, RecursionError):
            findings.add(SensitiveFinding(relative, 0, "scan_error"))
        else:
            findings.update(_scan_structured_value(parsed, relative))
    elif suffix in {".yaml", ".yml"}:
        try:
            yaml_node = compose(text)
            if yaml_node is not None and _yaml_structure_is_unsafe(yaml_node):
                raise DuplicateStructuredKeyError
            parsed = safe_load(text)
        except (YAMLError, DuplicateStructuredKeyError, RecursionError):
            findings.add(SensitiveFinding(relative, 0, "scan_error"))
        else:
            findings.update(_scan_structured_value(parsed, relative))
    elif suffix == ".toml":
        try:
            parsed = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, RecursionError):
            findings.add(SensitiveFinding(relative, 0, "scan_error"))
        else:
            findings.update(_scan_structured_value(parsed, relative))
    return findings


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError:
        return path.name


def scan_paths(paths: Iterable[Path], *, root: Path) -> list[SensitiveFinding]:
    """Scan text files and return only safe metadata about secret-like content."""

    findings: set[SensitiveFinding] = set()
    for path in sorted(paths):
        relative = _relative_path(path, root)
        if path.is_symlink():
            findings.add(SensitiveFinding(relative, 0, "symlink_not_scanned"))
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            with path.open("rb") as binary_stream:
                recognized_binary = _is_recognized_binary(binary_stream.read(16))
            if size > MAX_TEXT_FILE_BYTES:
                if not recognized_binary:
                    findings.add(SensitiveFinding(relative, 0, "oversized_text_file"))
                continue
            content = path.read_bytes()
        except OSError:
            findings.add(SensitiveFinding(relative, 0, "scan_error"))
            continue

        findings.update(_scan_content(content, relative, recognized_binary=recognized_binary))

    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


def _git_visible_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-per-directory=.gitignore",
            "-z",
        ],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualityCheckError("git ls-files could not enumerate repository content")

    return [root / os.fsdecode(raw_path) for raw_path in completed.stdout.split(b"\0") if raw_path]


def _git_index_entries(root: Path) -> list[GitIndexEntry]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualityCheckError("git ls-files could not inspect repository file modes")

    entries: list[GitIndexEntry] = []
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        if not separator:
            raise QualityCheckError("git ls-files returned an invalid stage record")
        fields = metadata.split(b" ")
        if len(fields) != 3 or fields[2] != b"0":
            raise QualityCheckError("git index contains an unsupported stage record")
        entries.append(
            GitIndexEntry(
                path=os.fsdecode(raw_path).replace("\\", "/"),
                mode=fields[0].decode("ascii"),
                object_id=fields[1].decode("ascii"),
            )
        )
    return sorted(entries, key=lambda entry: entry.path)


def _read_exact(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise QualityCheckError("git cat-file returned a truncated index blob")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _discard_exact(stream: IO[bytes], size: int) -> None:
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining, 64 * 1024))
        if not chunk:
            raise QualityCheckError("git cat-file returned a truncated index blob")
        remaining -= len(chunk)


def _scan_git_index(root: Path) -> set[SensitiveFinding]:
    findings: set[SensitiveFinding] = set()
    ordinary_entries: list[GitIndexEntry] = []
    for entry in _git_index_entries(root):
        if entry.mode == "120000":
            findings.add(SensitiveFinding(entry.path, 0, "symlink_not_scanned"))
        elif entry.mode not in {"100644", "100755"}:
            findings.add(SensitiveFinding(entry.path, 0, "unsupported_git_mode"))
        else:
            ordinary_entries.append(entry)

    if not ordinary_entries:
        return findings

    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if process.stdin is None or process.stdout is None:
        process.terminate()
        raise QualityCheckError("git cat-file did not expose batch streams")

    try:
        for entry in ordinary_entries:
            process.stdin.write(f"{entry.object_id}\n".encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().rstrip(b"\n")
            fields = header.split(b" ")
            if len(fields) != 3 or fields[1] != b"blob":
                raise QualityCheckError("git cat-file returned an invalid batch header")
            try:
                size = int(fields[2])
            except ValueError as error:
                raise QualityCheckError(
                    "git cat-file returned an invalid index blob size"
                ) from error

            prefix_size = min(size, 16)
            prefix = _read_exact(process.stdout, prefix_size)
            if size > MAX_TEXT_FILE_BYTES:
                _discard_exact(process.stdout, size - prefix_size)
                if not _is_recognized_binary(prefix):
                    findings.add(SensitiveFinding(entry.path, 0, "oversized_text_file"))
            else:
                content = prefix + _read_exact(process.stdout, size - prefix_size)
                findings.update(
                    _scan_content(
                        content,
                        entry.path,
                        recognized_binary=_is_recognized_binary(prefix),
                    )
                )
            if _read_exact(process.stdout, 1) != b"\n":
                raise QualityCheckError("git cat-file returned an invalid blob separator")

        process.stdin.close()
        if process.wait() != 0:
            raise QualityCheckError("git cat-file could not read index blobs")
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        process.wait()
    return findings


def scan_repository(root: Path) -> list[SensitiveFinding]:
    """Scan tracked and untracked-but-visible repository files."""

    findings = set(scan_paths(_git_visible_files(root), root=root))
    findings.update(_scan_git_index(root))
    return sorted(findings, key=lambda finding: (finding.path, finding.line, finding.rule))


def _run_command(label: str, command: Sequence[str], root: Path) -> None:
    print(f"[quality] {label}", flush=True)
    try:
        completed = subprocess.run(command, cwd=root, check=False)
    except OSError as error:
        raise QualityCheckError(f"{label} could not start") from error
    if completed.returncode != 0:
        raise QualityCheckError(f"{label} failed with exit code {completed.returncode}")


def _check_repository_policies(root: Path, phase: str) -> None:
    print(f"[quality] ignore-policy-{phase}", flush=True)
    ignore_violations = find_ignore_violations(root)
    if ignore_violations:
        raise QualityCheckError("; ".join(ignore_violations))

    print(f"[quality] sensitive-information-{phase}", flush=True)
    findings = scan_repository(root)
    if findings:
        descriptions = "; ".join(finding.safe_description() for finding in findings)
        raise QualityCheckError(f"sensitive information findings: {descriptions}")


def run_quality(root: Path = PROJECT_ROOT) -> None:
    """Run all offline checks and fail with secret-safe diagnostics."""

    _check_repository_policies(root, "preflight")

    for label, command in quality_commands():
        _run_command(label, command, root)

    _check_repository_policies(root, "final")
    print("[quality] all checks passed", flush=True)


def main() -> int:
    """Run the gate and return a shell-friendly, secret-safe exit code."""

    try:
        run_quality()
    except QualityCheckError as error:
        print(f"[quality] failed: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("[quality] failed: a required local tool could not start", file=sys.stderr)
        return 1
    return 0
