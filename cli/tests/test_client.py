"""Unit tests for cloudctl.client — exercised entirely against a faked
urllib.request.urlopen, so these never need a real API running."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any
from unittest.mock import patch

import pytest
from cloudctl.client import ApiClient, CloudctlAPIError


class _FakeResponse:
    """Stands in for the context-manager object urllib.request.urlopen
    returns — a plain BytesIO can't be used with `with obj:` because the
    `with` statement looks up __enter__/__exit__ on the type, not the
    instance."""

    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _ok_response(payload: Any) -> _FakeResponse:
    return _FakeResponse(payload)


def test_list_buckets_returns_items() -> None:
    client = ApiClient()
    with patch(
        "cloudctl.client.urllib.request.urlopen", return_value=_ok_response({"items": [{"name": "a"}]})
    ):
        assert client.list_buckets() == [{"name": "a"}]


def test_create_failure_sends_expected_body_and_resolves_alias() -> None:
    client = ApiClient()
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["body"] = json.loads(request.data)
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        return _ok_response(
            {"id": "fr-1", "service": "s3", "operation": "CreateBucket", "failure": "http_500"}
        )

    with patch("cloudctl.client.urllib.request.urlopen", side_effect=fake_urlopen):
        rule = client.create_failure(service="s3", operation="CreateBucket", failure="500")

    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost:8000/api/dev/failures"
    assert captured["body"]["failure"] == "http_500"  # alias resolved before sending
    assert rule["id"] == "fr-1"


def test_http_error_with_app_error_envelope_becomes_readable_message() -> None:
    client = ApiClient()
    body = json.dumps(
        {"error": {"code": "RESOURCE_NOT_FOUND", "message": "No such rule.", "retryable": False}}
    )
    error = urllib.error.HTTPError(
        url="http://localhost:8000/api/dev/failures/fr-9",
        code=404,
        msg="Not Found",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body.encode("utf-8")),
    )

    with patch("cloudctl.client.urllib.request.urlopen", side_effect=error):
        with pytest.raises(CloudctlAPIError) as exc_info:
            client.delete_failure("fr-9")

    assert "No such rule." in str(exc_info.value)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


def test_unreachable_api_raises_readable_error() -> None:
    client = ApiClient(base_url="http://localhost:8000")
    with patch(
        "cloudctl.client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        with pytest.raises(CloudctlAPIError) as exc_info:
            client.health()

    assert "Could not reach the API" in str(exc_info.value)
    assert "cloudctl up" in str(exc_info.value)


def test_failure_alias_500_and_403_resolve() -> None:
    client = ApiClient()
    seen: list[str] = []

    def fake_urlopen(request, timeout):  # noqa: ANN001
        seen.append(json.loads(request.data)["failure"])
        return _ok_response({})

    with patch("cloudctl.client.urllib.request.urlopen", side_effect=fake_urlopen):
        client.create_failure(service="s3", operation="*", failure="500")
        client.create_failure(service="s3", operation="*", failure="403")
        client.create_failure(service="s3", operation="*", failure="throttle")

    assert seen == ["http_500", "http_403", "throttle"]
