"""Static delivery-boundary checks for the GitHub Actions quality workflow."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "quality.yml"


def test_ci_installs_the_pinned_official_godot_archive() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "https://github.com/godotengine/godot-builds/releases/download/"
        "4.7.2-stable/Godot_v4.7.2-stable_linux.x86_64.zip"
    ) in workflow
    assert "cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4" in workflow
    assert "sha256sum --check" in workflow
    assert "CYBER_TOWN_GODOT=" in workflow


def test_ci_keeps_read_only_no_secret_delivery_boundary() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "pull_request_target" not in workflow
    assert "secrets." not in workflow
    assert "permissions: write" not in workflow
    assert "services:" not in workflow
