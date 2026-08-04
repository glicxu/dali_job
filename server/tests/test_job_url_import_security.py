from __future__ import annotations

import socket
import time
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException, status

from app.modules.resume_job_match import job_url_import


PUBLIC_IP = "93.184.216.34"


def _destination(url: str) -> job_url_import.ValidatedDestination:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return job_url_import.ValidatedDestination(
        url=url,
        scheme=parsed.scheme,
        hostname=parsed.hostname or "public.example",
        port=443 if parsed.scheme == "https" else 80,
        addresses=(PUBLIC_IP,),
        request_target=path,
    )


def _response(
    status_code: int = 200,
    *,
    headers: tuple[tuple[str, str], ...] = (("Content-Type", "text/html; charset=utf-8"),),
    body: bytes = b"<html><body>job</body></html>",
) -> job_url_import.NetworkResponse:
    return job_url_import.NetworkResponse(
        status_code=status_code,
        reason="OK" if status_code < 400 else "Error",
        headers=headers,
        body=body,
    )


def _public_resolver(hostname: str, _port: int) -> tuple[str, ...]:
    if hostname == "public.example":
        return (PUBLIC_IP,)
    return job_url_import._resolve_public_addresses(hostname, _port)


@pytest.mark.parametrize(
    "url, expected_detail",
    [
        ("https://user:password@example.com/job", "embedded credentials"),
        ("https://example.com:8443/job", "nonstandard port"),
        ("http://example.com:443/job", "nonstandard port"),
        ("http://./job", "host is invalid"),
    ],
)
def test_destination_rejects_credentials_and_nonstandard_ports(url: str, expected_detail: str) -> None:
    with pytest.raises(HTTPException) as caught:
        job_url_import.validate_public_job_url(url)

    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert expected_detail in str(caught.value.detail)


@pytest.mark.parametrize(
    ("url", "resolved_ip"),
    [
        ("http://127.1/jobs", "127.0.0.1"),
        ("http://2130706433/jobs", "127.0.0.1"),
        ("http://0x7f000001/jobs", "127.0.0.1"),
        ("http://[::ffff:127.0.0.1]/jobs", "::ffff:127.0.0.1"),
    ],
)
def test_destination_rejects_alternate_loopback_encodings(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    resolved_ip: str,
) -> None:
    family = socket.AF_INET6 if ":" in resolved_ip else socket.AF_INET
    socket_address = (resolved_ip, 80, 0, 0) if family == socket.AF_INET6 else (resolved_ip, 80)
    monkeypatch.setattr(
        job_url_import.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)],
    )

    with pytest.raises(HTTPException) as caught:
        job_url_import.validate_public_job_url(url)

    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "not allowed" in str(caught.value.detail)


@pytest.mark.parametrize(
    "redirect_target",
    [
        "http://127.0.0.1/admin",
        "http://10.20.30.40/internal",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_static_fetch_rejects_redirects_to_nonpublic_targets(
    monkeypatch: pytest.MonkeyPatch,
    redirect_target: str,
) -> None:
    def fake_fetch(url: str, **_kwargs):
        return _destination(url), _response(
            302,
            headers=(("Location", redirect_target), ("Content-Type", "text/html")),
            body=b"",
        )

    monkeypatch.setattr(job_url_import, "_fetch_single_response", fake_fetch)

    with pytest.raises(HTTPException) as caught:
        job_url_import._fetch_url_text("https://public.example/job")

    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "not allowed" in str(caught.value.detail)


def test_static_fetch_revalidates_each_redirect_in_public_to_private_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_resolver = job_url_import._resolve_public_addresses

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        if hostname == "public.example":
            return (PUBLIC_IP,)
        return original_resolver(hostname, port)

    calls: list[str] = []

    def fake_fetch(url: str, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            location = "https://public.example/second"
        else:
            location = "http://169.254.169.254/latest/meta-data"
        return _destination(url), _response(
            302,
            headers=(("Location", location), ("Content-Type", "text/html")),
            body=b"",
        )

    monkeypatch.setattr(job_url_import, "_resolve_public_addresses", resolver)
    monkeypatch.setattr(job_url_import, "_fetch_single_response", fake_fetch)

    with pytest.raises(HTTPException) as caught:
        job_url_import._fetch_url_text("https://public.example/first")

    assert calls == ["https://public.example/first", "https://public.example/second"]
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "not allowed" in str(caught.value.detail)


def test_static_fetch_limits_redirect_count(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, **_kwargs):
        calls.append(url)
        return _destination(url), _response(
            302,
            headers=(("Location", f"https://public.example/{len(calls)}"), ("Content-Type", "text/html")),
            body=b"",
        )

    monkeypatch.setattr(job_url_import, "_resolve_public_addresses", _public_resolver)
    monkeypatch.setattr(job_url_import, "_fetch_single_response", fake_fetch)

    with pytest.raises(HTTPException) as caught:
        job_url_import._fetch_url_text("https://public.example/start")

    assert caught.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "too many redirects" in str(caught.value.detail)
    assert len(calls) == job_url_import.MAX_REDIRECTS + 1


class _StreamingResponse:
    status = 200
    reason = "OK"

    def __init__(self, body: bytes, content_length: str | None = None) -> None:
        self.headers = {} if content_length is None else {"content-length": content_length}
        self._body = body
        self._offset = 0

    def read(self, size: int) -> bytes:
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self.headers.items())


def test_response_reader_rejects_declared_and_streamed_oversized_bodies() -> None:
    deadline = time.monotonic() + 5
    with pytest.raises(HTTPException) as declared:
        job_url_import._read_response_body(
            _StreamingResponse(b"", content_length="9"),
            max_bytes=8,
            deadline=deadline,
        )
    assert declared.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE

    with pytest.raises(HTTPException) as streamed:
        job_url_import._read_response_body(
            _StreamingResponse(b"123456789"),
            max_bytes=8,
            deadline=deadline,
        )
    assert streamed.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE


def test_network_request_uses_validated_ip_without_second_dns_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeConnection:
        def __init__(self, hostname: str, port: int, address: str, timeout: float) -> None:
            captured.update(hostname=hostname, port=port, address=address, timeout=timeout)

        def request(self, method: str, target: str, headers: dict[str, str]) -> None:
            captured.update(method=method, target=target, headers=headers)

        def getresponse(self) -> _StreamingResponse:
            return _StreamingResponse(b"ok", content_length="2")

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(job_url_import, "_PinnedHTTPConnection", FakeConnection)
    monkeypatch.setattr(
        job_url_import.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("DNS must not be repeated")),
    )
    destination = job_url_import.ValidatedDestination(
        url="http://public.example/job",
        scheme="http",
        hostname="public.example",
        port=80,
        addresses=(PUBLIC_IP,),
        request_target="/job",
    )

    response = job_url_import._request_validated_destination(
        destination,
        method="GET",
        headers={"Host": "public.example"},
        max_bytes=8,
        deadline=time.monotonic() + 5,
    )

    assert captured["address"] == PUBLIC_IP
    assert captured["target"] == "/job"
    assert captured["closed"] is True
    assert response.body == b"ok"


class _BrowserRequest:
    def __init__(self, url: str, *, resource_type: str = "document", method: str = "GET") -> None:
        self.url = url
        self.resource_type = resource_type
        self.method = method
        self.headers: dict[str, str] = {}


class _BrowserRoute:
    def __init__(self, request: _BrowserRequest) -> None:
        self.request = request
        self.aborted = False
        self.fulfilled: dict[str, object] | None = None

    def abort(self) -> None:
        self.aborted = True

    def fulfill(self, **kwargs) -> None:
        self.fulfilled = kwargs


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1/internal",
        "http://10.0.0.5/private",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_browser_proxy_blocks_nonpublic_frames_and_subrequests(unsafe_url: str) -> None:
    route = _BrowserRoute(_BrowserRequest(unsafe_url, resource_type="iframe"))
    budget = job_url_import.RenderedFetchBudget(deadline=time.monotonic() + 5)

    job_url_import._proxy_browser_route(route, budget)

    assert route.aborted is True
    assert route.fulfilled is None
    assert budget.blocked_status_code == status.HTTP_400_BAD_REQUEST
    assert budget.blocked_reason is not None


def test_browser_proxy_validates_redirect_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    original_resolver = job_url_import._resolve_public_addresses

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        if hostname == "public.example":
            return (PUBLIC_IP,)
        return original_resolver(hostname, port)

    def fake_fetch(url: str, **_kwargs):
        return _destination(url), _response(
            302,
            headers=(("Location", "http://169.254.169.254/latest/meta-data"),),
            body=b"",
        )

    monkeypatch.setattr(job_url_import, "_resolve_public_addresses", resolver)
    monkeypatch.setattr(job_url_import, "_fetch_single_response", fake_fetch)
    route = _BrowserRoute(_BrowserRequest("https://public.example/job"))
    budget = job_url_import.RenderedFetchBudget(deadline=time.monotonic() + 5)

    job_url_import._proxy_browser_route(route, budget)

    assert route.aborted is True
    assert route.fulfilled is None
    assert budget.blocked_reason is not None
    assert "not allowed" in budget.blocked_reason


def test_browser_proxy_limits_total_subrequests() -> None:
    route = _BrowserRoute(_BrowserRequest("https://public.example/asset.js", resource_type="script"))
    budget = job_url_import.RenderedFetchBudget(
        deadline=time.monotonic() + 5,
        requests=job_url_import.MAX_RENDERED_SUBREQUESTS,
    )

    job_url_import._proxy_browser_route(route, budget)

    assert route.aborted is True
    assert route.fulfilled is None
    assert budget.blocked_status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert budget.requests == job_url_import.MAX_RENDERED_SUBREQUESTS + 1


def test_browser_proxy_limits_total_response_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_url_import, "_resolve_public_addresses", _public_resolver)
    route = _BrowserRoute(_BrowserRequest("https://public.example/asset.js", resource_type="script"))
    budget = job_url_import.RenderedFetchBudget(
        deadline=time.monotonic() + 5,
        response_bytes=job_url_import.MAX_RENDERED_TOTAL_BYTES,
    )

    job_url_import._proxy_browser_route(route, budget)

    assert route.aborted is True
    assert route.fulfilled is None
    assert budget.blocked_status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert budget.blocked_reason is not None
