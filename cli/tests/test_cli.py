"""Unit tests for cloudctl.__main__ — argument parsing and dispatch.

Every command handler is exercised with `find_project_root`, `run_script`,
`compose`, and `ApiClient` all patched out, so these tests never touch
Docker, a real script, or a real HTTP server.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cloudctl.__main__ import main
from cloudctl.client import CloudctlAPIError
from cloudctl.compose import ProjectNotFoundError

FAKE_ROOT = Path("/fake/repo")


@pytest.fixture(autouse=True)
def _fake_project_root():
    with patch("cloudctl.__main__.find_project_root", return_value=FAKE_ROOT):
        yield


def test_up_delegates_to_dev_up_script() -> None:
    with patch("cloudctl.__main__.run_script", return_value=0) as mock_run:
        assert main(["up"]) == 0
    mock_run.assert_called_once_with(FAKE_ROOT, "dev-up.sh")


def test_down_passes_volumes_flag_through() -> None:
    with patch("cloudctl.__main__.run_script", return_value=0) as mock_run:
        main(["down", "--volumes"])
    mock_run.assert_called_once_with(FAKE_ROOT, "dev-down.sh", "--volumes")


def test_down_without_flag_passes_no_extra_args() -> None:
    with patch("cloudctl.__main__.run_script", return_value=0) as mock_run:
        main(["down"])
    mock_run.assert_called_once_with(FAKE_ROOT, "dev-down.sh")


def test_test_command_maps_flags_to_script_args_and_env() -> None:
    with patch("cloudctl.__main__.run_script", return_value=0) as mock_run:
        main(["test", "--skip-e2e", "--keep-up"])
    mock_run.assert_called_once_with(FAKE_ROOT, "verify-all.sh", "--keep-up", env={"SKIP_E2E": "1"})


def test_test_command_defaults_run_everything() -> None:
    with patch("cloudctl.__main__.run_script", return_value=0) as mock_run:
        main(["test"])
    mock_run.assert_called_once_with(FAKE_ROOT, "verify-all.sh", env={})


def test_a_failing_script_exit_code_propagates() -> None:
    with patch("cloudctl.__main__.run_script", return_value=17):
        assert main(["seed"]) == 17


def test_logs_with_service_and_follow() -> None:
    with patch("cloudctl.__main__.compose", return_value=0) as mock_compose:
        main(["logs", "api", "--follow"])
    mock_compose.assert_called_once_with(FAKE_ROOT, "logs", "-f", "api")


def test_status_reports_unreachable_api_but_keeps_compose_exit_code() -> None:
    fake_client = MagicMock()
    fake_client.health.side_effect = CloudctlAPIError("Could not reach the API at http://x (refused).")
    with (
        patch("cloudctl.__main__.compose", return_value=0),
        patch("cloudctl.__main__.ApiClient", return_value=fake_client),
    ):
        assert main(["status"]) == 1


def test_resources_prints_tables_from_the_api(capsys: pytest.CaptureFixture[str]) -> None:
    fake_client = MagicMock()
    fake_client.list_buckets.return_value = [{"name": "demo-assets", "region": "us-east-1"}]
    fake_client.list_queues.return_value = []
    fake_client.list_tables.return_value = []
    with patch("cloudctl.__main__.ApiClient", return_value=fake_client):
        assert main(["resources"]) == 0

    out = capsys.readouterr().out
    assert "demo-assets" in out
    assert "S3 buckets:" in out


def test_resources_filters_to_one_service() -> None:
    fake_client = MagicMock()
    fake_client.list_queues.return_value = []
    with patch("cloudctl.__main__.ApiClient", return_value=fake_client):
        main(["resources", "--service", "sqs"])

    fake_client.list_buckets.assert_not_called()
    fake_client.list_tables.assert_not_called()
    fake_client.list_queues.assert_called_once()


def test_resources_reports_api_errors_and_exits_nonzero() -> None:
    fake_client = MagicMock()
    fake_client.list_buckets.side_effect = CloudctlAPIError("boom")
    with patch("cloudctl.__main__.ApiClient", return_value=fake_client):
        assert main(["resources"]) == 1


def test_failure_inject_passes_positional_args_and_flags_to_the_client() -> None:
    fake_client = MagicMock()
    fake_client.create_failure.return_value = {
        "id": "fr-1",
        "service": "s3",
        "operation": "CreateBucket",
        "failure": "http_500",
    }
    with patch("cloudctl.__main__.ApiClient", return_value=fake_client):
        assert (
            main(
                [
                    "failure",
                    "inject",
                    "s3",
                    "CreateBucket",
                    "500",
                    "--delay-ms",
                    "250",
                    "--probability",
                    "0.5",
                ]
            )
            == 0
        )

    fake_client.create_failure.assert_called_once_with(
        service="s3", operation="CreateBucket", failure="500", delay_ms=250, probability=0.5
    )


def test_failure_clear_and_delete() -> None:
    fake_client = MagicMock()
    with patch("cloudctl.__main__.ApiClient", return_value=fake_client):
        main(["failure", "clear"])
        main(["failure", "delete", "fr-3"])

    fake_client.clear_failures.assert_called_once()
    fake_client.delete_failure.assert_called_once_with("fr-3")


def test_api_url_flag_overrides_default() -> None:
    with patch("cloudctl.__main__.ApiClient") as mock_client_cls:
        mock_client_cls.return_value.list_failures.return_value = []
        main(["--api-url", "http://example.com:9000", "failure", "list"])

    mock_client_cls.assert_called_once_with(base_url="http://example.com:9000")


def test_api_url_env_var_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDCTL_API_URL", "http://env-host:8000")
    with patch("cloudctl.__main__.ApiClient") as mock_client_cls:
        mock_client_cls.return_value.list_failures.return_value = []
        main(["failure", "list"])

    mock_client_cls.assert_called_once_with(base_url="http://env-host:8000")


def test_project_not_found_is_reported_cleanly_instead_of_raising() -> None:
    with patch("cloudctl.__main__.find_project_root", side_effect=ProjectNotFoundError("nope")):
        assert main(["up"]) == 1


def test_missing_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit):
        main([])
