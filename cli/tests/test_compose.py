"""Unit tests for cloudctl.compose — project-root discovery and the
subprocess wrappers, without ever actually invoking docker or a real
script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from cloudctl.compose import ProjectNotFoundError, compose, find_project_root, run_script


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "scripts").mkdir()
    return tmp_path


def test_find_project_root_from_repo_root(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert find_project_root(start=repo) == repo


def test_find_project_root_walks_upward_from_a_subdirectory(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    nested = repo / "app" / "api"
    nested.mkdir(parents=True)
    assert find_project_root(start=nested) == repo


def test_find_project_root_raises_when_nothing_found(tmp_path: Path) -> None:
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    with pytest.raises(ProjectNotFoundError):
        find_project_root(start=empty)


def test_find_project_root_honors_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("CLOUDCTL_PROJECT_ROOT", str(repo))
    # Even starting somewhere with no docker-compose.yml at all, the
    # override should win outright.
    elsewhere = tmp_path.parent
    assert find_project_root(start=elsewhere) == repo


def test_find_project_root_env_override_without_compose_file_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLOUDCTL_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(ProjectNotFoundError):
        find_project_root()


def test_run_script_invokes_the_scripts_directory_executable(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch("cloudctl.compose.subprocess.call", return_value=0) as mock_call:
        exit_code = run_script(repo, "seed.sh", "--extra")

    assert exit_code == 0
    args, kwargs = mock_call.call_args
    assert args[0] == [str(repo / "scripts" / "seed.sh"), "--extra"]
    assert kwargs["cwd"] == repo


def test_run_script_merges_extra_env(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch("cloudctl.compose.subprocess.call", return_value=0) as mock_call:
        run_script(repo, "verify-all.sh", env={"SKIP_E2E": "1"})

    _, kwargs = mock_call.call_args
    assert kwargs["env"]["SKIP_E2E"] == "1"


def test_compose_calls_docker_compose_in_repo_root(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    with patch("cloudctl.compose.subprocess.call", return_value=0) as mock_call:
        compose(repo, "ps")

    args, kwargs = mock_call.call_args
    assert args[0] == ["docker", "compose", "ps"]
    assert kwargs["cwd"] == repo
