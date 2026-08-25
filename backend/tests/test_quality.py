from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import cyber_town.quality as quality
from cyber_town.config import Settings
from cyber_town.contracts.export import render_schemas
from cyber_town.quality import (
    PROJECT_ROOT,
    QualityCheckError,
    SensitiveFinding,
    find_ignore_violations,
    quality_commands,
    scan_paths,
    scan_repository,
)


def test_project_ignore_contract_is_complete() -> None:
    assert find_ignore_violations(PROJECT_ROOT) == []


def test_missing_ignore_rule_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)

    violations = find_ignore_violations(tmp_path)

    assert any(".env" in violation for violation in violations)


def test_tracked_ignored_runtime_files_are_reported(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    protected = (".env", "data/runtime.db", "logs/dialogue.jsonl")
    for relative in protected:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic\n", encoding="utf-8")
        subprocess.run(["git", "add", "--force", relative], cwd=tmp_path, check=True)

    violations = find_ignore_violations(tmp_path)

    for relative in protected:
        assert f"ignored path is tracked: {relative}" in violations


def test_missing_gitignore_from_index_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)

    assert "index .gitignore is missing" in find_ignore_violations(tmp_path)


def test_staged_gitignore_policy_is_checked_when_worktree_is_clean(tmp_path: Path) -> None:
    safe_policy = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(safe_policy, encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    gitignore.write_text(safe_policy + "\nextra.log\n", encoding="utf-8")
    (tmp_path / "extra.log").write_text("synthetic\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--force", "extra.log"], cwd=tmp_path, check=True)
    gitignore.write_text(safe_policy, encoding="utf-8")

    violations = find_ignore_violations(tmp_path)

    assert "index ignored path is tracked: extra.log" in violations


@pytest.mark.parametrize(
    "name",
    [
        "API_KEY",
        "TOKEN",
        "PASSWORD",
        "SECRET",
        "PRIVATE_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "llm_api_key",
    ],
)
def test_real_looking_credential_is_detected_without_echoing_value(
    tmp_path: Path,
    name: str,
) -> None:
    synthetic_value = "ghp_" + ("a" * 36)
    secret_file = tmp_path / "local.env"
    secret_file.write_text(f"{name}={synthetic_value}\n", encoding="utf-8")

    findings = scan_paths([secret_file], root=tmp_path)
    rendered = "\n".join(finding.safe_description() for finding in findings)

    assert findings
    assert "credential_assignment" in rendered or "github_token" in rendered
    assert synthetic_value not in rendered


def test_empty_and_documented_placeholder_credentials_are_allowed(tmp_path: Path) -> None:
    placeholder_file = tmp_path / ".env.example"
    placeholder_file.write_text(
        "LLM_API_KEY=\nGITHUB_TOKEN=your-token-here\n",
        encoding="utf-8",
    )

    assert scan_paths([placeholder_file], root=tmp_path) == []


def test_placeholder_substrings_do_not_hide_real_looking_credentials(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.env"
    candidate.write_text(
        "DATABASE_URL=postgresql://user:real-example-password@db.invalid/app\n",
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


def test_placeholder_prefixes_do_not_hide_real_looking_credentials(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.env"
    candidate.write_text(
        "DATABASE_URL=your-production-database-value-938475\n",
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


@pytest.mark.parametrize(
    "value",
    [
        "your-token-here#synthetic-real-value-938475",
        '"your-token-here#synthetic-real-value-938475"',
    ],
)
def test_hash_characters_do_not_truncate_credential_values(
    tmp_path: Path,
    value: str,
) -> None:
    candidate = tmp_path / "settings.env"
    candidate.write_text(f"LLM_API_KEY={value}\n", encoding="utf-8")

    assert scan_paths([candidate], root=tmp_path)


def test_multiline_dotenv_credentials_are_parsed_as_one_value(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.env"
    candidate.write_text(
        'PASSWORD="changeme\nsynthetic-real-value-938475"\n',
        encoding="utf-8",
    )

    assert SensitiveFinding("settings.env", 1, "credential_assignment") in scan_paths(
        [candidate], root=tmp_path
    )


def test_lowercase_credential_names_are_detected(tmp_path: Path) -> None:
    candidate = tmp_path / "lower.env"
    candidate.write_text(
        "llm_api_key=synthetic-but-not-placeholder-value-938475\n",
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


def test_non_utf8_text_candidates_fail_closed(tmp_path: Path) -> None:
    candidate = tmp_path / "utf16.env"
    candidate.write_text("LLM_API_KEY=synthetic-utf16-value\n", encoding="utf-16")

    findings = scan_paths([candidate], root=tmp_path)

    assert [finding.rule for finding in findings] == ["scan_error"]


def test_utf8_bom_does_not_hide_first_line_credentials(tmp_path: Path) -> None:
    candidate = tmp_path / "bom.env"
    candidate.write_text(
        "LLM_API_KEY=synthetic-bom-value-938475\n",
        encoding="utf-8-sig",
    )

    assert scan_paths([candidate], root=tmp_path)


def test_text_with_binary_extension_is_still_scanned(tmp_path: Path) -> None:
    candidate = tmp_path / "asset.png"
    candidate.write_text(
        "LLM_API_KEY=synthetic-text-disguised-as-png-938475\n",
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


def test_recognized_binary_magic_is_skipped(tmp_path: Path) -> None:
    candidate = tmp_path / "asset.data"
    candidate.write_bytes(b"\x89PNG\r\n\x1a\n\x00synthetic-binary-data")

    assert scan_paths([candidate], root=tmp_path) == []


def test_recognized_binary_magic_does_not_hide_plaintext_credentials(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "asset.gif"
    candidate.write_bytes(b"GIF89a\nLLM_API_KEY=synthetic-binary-polyglot-secret-value-938475\n")

    assert scan_paths([candidate], root=tmp_path)


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_mapping_style_credentials_are_detected(tmp_path: Path, suffix: str) -> None:
    candidate = tmp_path / f"settings{suffix}"
    candidate.write_text(
        '"LLM_API_KEY": "synthetic-mapping-secret-value-938475"\n',
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


def test_multiline_yaml_credentials_are_parsed_as_one_value(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.yaml"
    candidate.write_text(
        'PASSWORD: "changeme\n  synthetic-real-value-938475"\n',
        encoding="utf-8",
    )

    assert SensitiveFinding("settings.yaml", 0, "credential_assignment") in scan_paths(
        [candidate], root=tmp_path
    )


def test_multiline_toml_credentials_are_parsed_as_one_value(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.toml"
    candidate.write_text(
        'PASSWORD = """changeme\nsynthetic-real-value-938475"""\n',
        encoding="utf-8",
    )

    assert SensitiveFinding("settings.toml", 0, "credential_assignment") in scan_paths(
        [candidate], root=tmp_path
    )


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("settings.json", '{"PASSWORD":"changeme"}\n'),
        ("settings.yaml", "PASSWORD: changeme\n"),
        ("settings.toml", 'PASSWORD = "changeme"\n'),
    ],
)
def test_structured_config_exact_placeholders_are_allowed(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    candidate = tmp_path / filename
    candidate.write_text(content, encoding="utf-8")

    assert scan_paths([candidate], root=tmp_path) == []


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("settings.env", "LLM_API_KEY=changeme # documented placeholder\n"),
        ("settings.toml", 'PASSWORD = "changeme" # documented placeholder\n'),
    ],
)
def test_semantic_config_comments_do_not_turn_placeholders_into_findings(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    candidate = tmp_path / filename
    candidate.write_text(content, encoding="utf-8")

    assert scan_paths([candidate], root=tmp_path) == []


def test_compact_json_credentials_after_other_fields_are_detected(tmp_path: Path) -> None:
    candidate = tmp_path / "settings.json"
    candidate.write_text(
        '{"safe":"synthetic","PASSWORD":"synthetic-compact-secret-value-938475"}\n',
        encoding="utf-8",
    )

    assert scan_paths([candidate], root=tmp_path)


@pytest.mark.parametrize(
    "value",
    ["changeme,synthetic-real-value-938475", "changeme}synthetic-real-value-938475"],
)
def test_json_delimiters_inside_credential_values_do_not_bypass_scan(
    tmp_path: Path,
    value: str,
) -> None:
    candidate = tmp_path / "settings.json"
    candidate.write_text(
        json.dumps({"PASSWORD": value}) + "\n",
        encoding="utf-8",
    )

    assert SensitiveFinding("settings.json", 0, "credential_assignment") in scan_paths(
        [candidate], root=tmp_path
    )


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        (
            "settings.json",
            '{"PASSWORD":"synthetic-real-value-938475","PASSWORD":"changeme"}\n',
        ),
        (
            "settings.yaml",
            "PASSWORD: synthetic-real-value-938475\nPASSWORD: changeme\n",
        ),
    ],
)
def test_duplicate_structured_keys_fail_closed(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    candidate = tmp_path / filename
    candidate.write_text(content, encoding="utf-8")

    assert SensitiveFinding(filename, 0, "scan_error") in scan_paths([candidate], root=tmp_path)


def test_recursive_yaml_alias_fails_closed(tmp_path: Path) -> None:
    candidate = tmp_path / "cycle.yaml"
    candidate.write_text("root: &loop [*loop]\n", encoding="utf-8")

    assert SensitiveFinding("cycle.yaml", 0, "scan_error") in scan_paths([candidate], root=tmp_path)


def test_excessively_nested_json_fails_closed(tmp_path: Path) -> None:
    candidate = tmp_path / "deep.json"
    candidate.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")

    assert SensitiveFinding("deep.json", 0, "scan_error") in scan_paths([candidate], root=tmp_path)


def test_oversized_text_candidates_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(quality, "MAX_TEXT_FILE_BYTES", 8)
    candidate = tmp_path / "large.txt"
    candidate.write_text("123456789", encoding="utf-8")

    findings = scan_paths([candidate], root=tmp_path)

    assert [finding.rule for finding in findings] == ["oversized_text_file"]


@pytest.mark.parametrize("worktree_placeholder", [False, True])
def test_git_index_symlinks_fail_closed_on_windows_style_worktrees(
    tmp_path: Path,
    worktree_placeholder: bool,
) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    blob = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=tmp_path,
            input=b"outside.txt",
            capture_output=True,
            check=True,
        )
        .stdout.decode("ascii")
        .strip()
    )
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"120000,{blob},linked.txt"],
        cwd=tmp_path,
        check=True,
    )
    if worktree_placeholder:
        (tmp_path / "linked.txt").write_text("outside.txt", encoding="utf-8")

    findings = scan_repository(tmp_path)

    assert SensitiveFinding("linked.txt", 0, "symlink_not_scanned") in findings


def test_staged_secrets_are_scanned_when_worktree_content_is_clean(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    candidate = tmp_path / "settings.env.example"
    candidate.write_text(
        "LLM_API_KEY=synthetic-staged-secret-value-938475\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "settings.env.example"], cwd=tmp_path, check=True)
    candidate.write_text("LLM_API_KEY=\n", encoding="utf-8")

    findings = scan_repository(tmp_path)

    assert SensitiveFinding("settings.env.example", 1, "credential_assignment") in findings


def test_staged_binary_polyglot_secrets_are_scanned_when_worktree_is_clean(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    candidate = tmp_path / "asset.gif"
    candidate.write_bytes(b"GIF89a\nLLM_API_KEY=synthetic-staged-polyglot-secret-value-938475\n")
    subprocess.run(["git", "add", "asset.gif"], cwd=tmp_path, check=True)
    candidate.write_bytes(b"GIF89a\nsynthetic-clean-content\n")

    findings = scan_repository(tmp_path)

    assert SensitiveFinding("asset.gif", 2, "credential_assignment") in findings


def test_worktree_secrets_are_scanned_when_index_content_is_clean(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    candidate = tmp_path / "settings.env.example"
    candidate.write_text("LLM_API_KEY=\n", encoding="utf-8")
    subprocess.run(["git", "add", "settings.env.example"], cwd=tmp_path, check=True)
    candidate.write_text(
        "LLM_API_KEY=synthetic-worktree-secret-value-938475\n",
        encoding="utf-8",
    )

    findings = scan_repository(tmp_path)

    assert SensitiveFinding("settings.env.example", 1, "credential_assignment") in findings


def test_oversized_staged_text_fails_closed_when_worktree_is_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(quality, "MAX_TEXT_FILE_BYTES", 8)
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    candidate = tmp_path / "large.txt"
    candidate.write_text("123456789", encoding="utf-8")
    subprocess.run(["git", "add", "large.txt"], cwd=tmp_path, check=True)
    candidate.write_text("ok", encoding="utf-8")

    findings = scan_repository(tmp_path)

    assert SensitiveFinding("large.txt", 0, "oversized_text_file") in findings


def test_oversized_staged_recognized_binary_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(quality, "MAX_TEXT_FILE_BYTES", 8)
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    candidate = tmp_path / "asset.data"
    candidate.write_bytes(b"\x89PNG\r\n\x1a\n\x00synthetic-binary-data")
    subprocess.run(["git", "add", "asset.data"], cwd=tmp_path, check=True)
    candidate.write_text("ok", encoding="utf-8")

    assert scan_repository(tmp_path) == []


def test_ignore_policy_isolated_from_global_excludes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitignore").write_text(
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    readme = tmp_path / "README.md"
    readme.write_text("synthetic\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "README.md"], cwd=tmp_path, check=True)
    excludes = tmp_path / "global-excludes"
    excludes.write_text("*.md\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.excludesFile")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(excludes))

    assert find_ignore_violations(tmp_path) == []


def test_ignore_policy_isolated_from_repository_info_exclude(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    readme = tmp_path / "README.md"
    readme.write_text("synthetic\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "README.md"], cwd=tmp_path, check=True)
    (tmp_path / ".git" / "info" / "exclude").write_text("*.md\n", encoding="utf-8")

    assert find_ignore_violations(tmp_path) == []


def test_repository_sensitive_scan_is_clean() -> None:
    assert scan_repository(PROJECT_ROOT) == []


def test_index_scan_uses_one_batch_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitignore").write_text(
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    for index in range(20):
        (tmp_path / f"file-{index}.txt").write_text("synthetic\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    original_popen = subprocess.Popen
    commands: list[tuple[str, ...]] = []

    def record_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        command = args[0]
        if isinstance(command, (list, tuple)):
            commands.append(tuple(str(part) for part in command))
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", record_popen)

    assert scan_repository(tmp_path) == []
    cat_file_commands = [command for command in commands if "cat-file" in command]
    assert cat_file_commands == [("git", "-C", str(tmp_path), "cat-file", "--batch")]


def test_local_policy_helpers_do_not_require_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in local quality checks")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    clean_file = tmp_path / "clean.txt"
    clean_file.write_text("local-only\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert Settings.model_validate({}).llm_api_key is None
    assert render_schemas()
    assert scan_paths([clean_file], root=tmp_path) == []


def test_quality_command_set_contains_no_network_client() -> None:
    commands = quality_commands(python="python", godot="godot")
    command_parts = {part.lower() for _, command in commands for part in command}

    assert command_parts.isdisjoint({"curl", "wget", "invoke-webrequest", "powershell"})
    assert [label for label, _ in commands] == [
        "lock",
        "ruff",
        "mypy",
        "schema",
        "godot-import",
        "godot-unit",
        "connectivity",
        "dialogue-connectivity",
        "pytest",
    ]
    assert commands[4][1] == (
        "godot",
        "--headless",
        "--editor",
        "--path",
        "game",
        "--quit",
    )
    assert commands[6][1] == (
        "python",
        "scripts/connectivity_integration.py",
        "--godot",
        "godot",
    )
    assert commands[7][1] == (
        "python",
        "scripts/dialogue_integration.py",
        "--godot",
        "godot",
    )


def test_quality_subprocesses_cannot_inherit_credentials_or_read_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setenv("LLM_API_KEY", "synthetic-inherited-provider-value")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def record_command(*_args: object, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs.get("env", {}))
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(subprocess, "run", record_command)

    quality._run_command("synthetic-isolation", ("synthetic-tool",), tmp_path)

    assert captured.get("CYBER_TOWN_DISABLE_DOTENV") == "1"
    assert captured.get("LLM_PROVIDER") == "disabled"
    assert "LLM_API_KEY" not in captured


def test_quality_runs_repository_policies_before_and_after_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    def record_ignore(_root: Path) -> list[str]:
        events.append("ignore")
        return []

    def record_sensitive(_root: Path) -> list[SensitiveFinding]:
        events.append("sensitive")
        return []

    monkeypatch.setattr(
        quality,
        "find_ignore_violations",
        record_ignore,
    )
    monkeypatch.setattr(
        quality,
        "scan_repository",
        record_sensitive,
    )
    monkeypatch.setattr(quality, "quality_commands", lambda: (("ruff", ("ruff",)),))
    monkeypatch.setattr(
        quality,
        "_run_command",
        lambda label, _command, _root: events.append(label),
    )

    quality.run_quality(tmp_path)

    assert events == ["ignore", "sensitive", "ruff", "ignore", "sensitive"]


def test_sensitive_preflight_stops_commands_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    synthetic_value = "synthetic-sensitive-preflight-value"
    monkeypatch.setattr(quality, "find_ignore_violations", lambda _root: [])
    monkeypatch.setattr(
        quality,
        "scan_repository",
        lambda _root: [SensitiveFinding("unsafe.py", 1, "credential_assignment")],
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("quality commands must not run before the sensitive preflight")

    monkeypatch.setattr(quality, "_run_command", fail_if_called)

    with pytest.raises(QualityCheckError) as captured:
        quality.run_quality(tmp_path)

    assert synthetic_value not in str(captured.value)


def test_command_failure_is_propagated_as_quality_error(tmp_path: Path) -> None:
    with pytest.raises(QualityCheckError, match="exit code 7"):
        quality._run_command(
            "synthetic-failure",
            (sys.executable, "-c", "raise SystemExit(7)"),
            tmp_path,
        )


def test_missing_command_is_propagated_as_quality_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def missing_command(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("synthetic missing tool")

    monkeypatch.setattr(subprocess, "run", missing_command)

    with pytest.raises(QualityCheckError, match="could not start"):
        quality._run_command("synthetic-missing", ("missing-tool",), tmp_path)


def test_main_returns_nonzero_with_safe_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    synthetic_value = "synthetic-main-secret-value"

    def fail_quality() -> None:
        raise QualityCheckError("safe failure metadata")

    monkeypatch.setattr(quality, "run_quality", fail_quality)

    assert quality.main() == 1
    captured = capsys.readouterr()
    assert "safe failure metadata" in captured.err
    assert synthetic_value not in captured.err


def test_main_redacts_unexpected_os_error_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    synthetic_value = "synthetic-os-error-sensitive-value"

    def fail_quality() -> None:
        raise OSError(synthetic_value)

    monkeypatch.setattr(quality, "run_quality", fail_quality)

    assert quality.main() == 1
    captured = capsys.readouterr()
    assert "required local tool could not start" in captured.err
    assert synthetic_value not in captured.err
