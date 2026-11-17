"""HTTP transport security, SSRF, DNS pinning, and fail-closed tests."""

from __future__ import annotations

import socket
from pathlib import Path

import httpcore
import httpx
import pytest

from homeagentp_core.modules.media import base as legacy_base
from homeagentp_core.modules.media import http_client as hc
from homeagentp_core.modules.media.adapter_base import MediaServiceAdapter
from homeagentp_core.modules.media.errors import (
    MediaMalformedResponseError,
    MediaSecurityError,
)
from homeagentp_core.modules.media.http_client import SafeMediaHttpClient
from homeagentp_core.modules.media.security import (
    resolve_and_validate_host,
    validate_resolved_dns,
    validate_service_url,
)


def test_ssrf_redirect_and_readonly_method_enforcement(tmp_path: Path) -> None:
    """Verify SSRF host allowlist, cloud metadata IP block, redirect block, and write block."""
    allowed = ["jellyfin", "qbittorrent", "127.0.0.1"]

    with pytest.raises(MediaSecurityError) as exc_host:
        validate_service_url("http://evil.example.com:8096", allowed)
    assert exc_host.value.error_code == "ssrf_blocked"

    with pytest.raises(MediaSecurityError) as exc_meta:
        validate_service_url("http://169.254.169.254/latest/meta-data", ["169.254.169.254"])
    assert exc_meta.value.error_code == "ssrf_blocked"

    with pytest.raises(MediaSecurityError) as exc_cred:
        validate_service_url("http://user:pass@jellyfin:8096", allowed)
    assert exc_cred.value.error_code == "ssrf_blocked"

    redirect_transport = httpx.MockTransport(
        lambda req: httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
    )
    client = SafeMediaHttpClient(
        base_url="http://jellyfin:8096",
        allowed_hosts=allowed,
        timeout_seconds=2.0,
        max_response_bytes=8192,
        allowed_get_prefixes=("/System/Info",),
        transport=redirect_transport,
    )
    with pytest.raises(MediaSecurityError) as exc_redir:
        client.get_json("/System/Info")
    assert exc_redir.value.error_code == "redirect_blocked"

    with pytest.raises(MediaSecurityError) as exc_write:
        client.request_raw("POST", "/api/v2/torrents/delete", form_data={"hashes": "all"})
    assert exc_write.value.error_code == "write_method_prohibited"


def test_r03_security_hardening_regressions(monkeypatch: pytest.MonkeyPatch) -> None:
    """R03: Verify segment-safe paths, IPv4-mapped IPv6, DNS SSRF, redirects, Content-Length."""
    assert legacy_base.SafeMediaHttpClient is SafeMediaHttpClient
    assert legacy_base.MediaServiceAdapter is MediaServiceAdapter
    assert legacy_base.MediaSecurityError is MediaSecurityError
    assert legacy_base.validate_service_url is validate_service_url

    client = SafeMediaHttpClient(
        base_url="http://jellyfin.local:8096",
        allowed_hosts=["jellyfin.local"],
        timeout_seconds=2.0,
        max_response_bytes=1024,
        allowed_get_prefixes=("/Sessions",),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[])),
    )
    assert client.get_json("/Sessions") == []
    assert client.get_json("/Sessions/active") == []

    for bad_path in (
        "/SessionsEvil",
        "/Sessions/%2e%2e/Users",
        "/Sessions?admin=1",
        "/Sessions#frag",
        "/Sessions\r\nX-Injected: 1",
    ):
        with pytest.raises(MediaSecurityError):
            client.get_json(bad_path)

    for mapped in (
        "http://[::ffff:169.254.169.254]:8096",
        "http://[::ffff:0.0.0.0]:8096",
    ):
        with pytest.raises(MediaSecurityError) as exc_info:
            validate_service_url(mapped, ["::ffff:169.254.169.254", "::ffff:0.0.0.0"])
        assert exc_info.value.error_code == "ssrf_blocked"

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
        ],
    )
    with pytest.raises(MediaSecurityError) as dns_exc:
        validate_resolved_dns("rebind.local")
    assert dns_exc.value.error_code == "ssrf_blocked"

    for code in (300, 307, 308):
        redir_client = SafeMediaHttpClient(
            base_url="http://jellyfin.local:8096",
            allowed_hosts=["jellyfin.local"],
            timeout_seconds=2.0,
            max_response_bytes=1024,
            allowed_get_prefixes=("/System/Info",),
            transport=httpx.MockTransport(
                lambda req, status=code: httpx.Response(
                    status, headers={"Location": "http://169.254.169.254/"}
                )
            ),
        )
        with pytest.raises(MediaSecurityError) as redir_exc:
            redir_client.get_json("/System/Info")
        assert redir_exc.value.error_code == "redirect_blocked"

    oversize_client = SafeMediaHttpClient(
        base_url="http://jellyfin.local:8096",
        allowed_hosts=["jellyfin.local"],
        timeout_seconds=2.0,
        max_response_bytes=512,
        allowed_get_prefixes=("/System/Info",),
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"Content-Length": "4096"}, content=b"{}")
        ),
    )
    with pytest.raises(MediaMalformedResponseError) as size_exc:
        oversize_client.get_json("/System/Info")
    assert size_exc.value.error_code == "response_too_large"


def test_r03_dns_pinning_fail_closed_and_rebinding_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify DNS fail-closed, single-lookup IP pinning against rebinding, and LAN/IPv6/SNI."""
    from httpcore._backends.sync import SyncBackend

    def _fail_dns(host: str, port: object, **kwargs: object) -> list[object]:
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _fail_dns)
    with pytest.raises(MediaSecurityError) as dns_fail_exc:
        validate_resolved_dns("nonexistent.local")
    assert dns_fail_exc.value.error_code == "dns_resolution_failed"

    client_fail = SafeMediaHttpClient(
        base_url="http://nonexistent.local:8096",
        allowed_hosts=["nonexistent.local"],
        timeout_seconds=2.0,
        max_response_bytes=1024,
        allowed_get_prefixes=("/System/Info",),
    )
    with pytest.raises(MediaSecurityError) as client_fail_exc:
        client_fail.get_json("/System/Info")
    assert client_fail_exc.value.error_code == "dns_resolution_failed"

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ],
    )
    with pytest.raises(MediaSecurityError) as mixed_exc:
        resolve_and_validate_host("dual.local", 8096)
    assert mixed_exc.value.error_code == "ssrf_blocked"

    dns_calls = 0

    def _rebinding_dns(host: str, port: object, **kwargs: object) -> list[object]:
        nonlocal dns_calls
        dns_calls += 1
        if dns_calls == 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _rebinding_dns)
    connected_targets: list[tuple[str, int]] = []
    tls_hostnames: list[object] = []

    class _FakeStream:
        def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
            return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"

        def write(self, buffer: bytes, timeout: float | None = None) -> None:
            return None

        def close(self) -> None:
            return None

        def start_tls(self, **kwargs: object) -> _FakeStream:
            tls_hostnames.append(kwargs.get("server_hostname"))
            return self

        def get_extra_info(self, info: str) -> object:
            return None

    def _fake_connect_tcp(
        self: SyncBackend,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> _FakeStream:
        connected_targets.append((host, port))
        return _FakeStream()

    monkeypatch.setattr(SyncBackend, "connect_tcp", _fake_connect_tcp)

    pinned_client = SafeMediaHttpClient(
        base_url="https://nas.local:8989",
        allowed_hosts=["nas.local"],
        timeout_seconds=2.0,
        max_response_bytes=1024,
        allowed_get_prefixes=("/System/Info",),
    )
    assert pinned_client.get_json("/System/Info") == {}
    assert dns_calls == 1
    assert connected_targets == [("192.168.1.50", 8989)]
    assert tls_hostnames == ["nas.local"]

    connected_targets.clear()
    ipv6_client = SafeMediaHttpClient(
        base_url="http://[fd00::10]:8096",
        allowed_hosts=["fd00::10"],
        timeout_seconds=2.0,
        max_response_bytes=1024,
        allowed_get_prefixes=("/System/Info",),
    )
    assert ipv6_client.get_json("/System/Info") == {}
    assert connected_targets == [("fd00::10", 8096)]


def test_r03_pinned_transport_fails_closed_on_incompatible_internals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_pinned_transport fails closed if httpx/httpcore internals are incompatible."""

    class _UnsupportedTransport:
        def __init__(self, **kwargs: object) -> None:
            self._pool = object()

    monkeypatch.setattr(httpx, "HTTPTransport", _UnsupportedTransport)
    with pytest.raises(MediaSecurityError) as pool_exc:
        hc._build_pinned_transport()
    assert pool_exc.value.error_code == "ssrf_pinning_unavailable"

    class _FakePoolNoBackend(httpcore.ConnectionPool):
        def __init__(self) -> None:
            pass

    class _NoBackendTransport:
        def __init__(self, **kwargs: object) -> None:
            self._pool = _FakePoolNoBackend()

    monkeypatch.setattr(httpx, "HTTPTransport", _NoBackendTransport)
    with pytest.raises(MediaSecurityError) as nb_exc:
        hc._build_pinned_transport()
    assert nb_exc.value.error_code == "ssrf_pinning_unavailable"

    class _ReadOnlyPool(httpcore.ConnectionPool):
        def __init__(self) -> None:
            self._orig = object()

        @property
        def _network_backend(self) -> object:
            return self._orig

        @_network_backend.setter
        def _network_backend(self, value: object) -> None:
            pass

    class _ReadOnlyTransport:
        def __init__(self, **kwargs: object) -> None:
            self._pool = _ReadOnlyPool()

    monkeypatch.setattr(httpx, "HTTPTransport", _ReadOnlyTransport)
    with pytest.raises(MediaSecurityError) as ro_exc:
        hc._build_pinned_transport()
    assert ro_exc.value.error_code == "ssrf_pinning_unavailable"

    monkeypatch.setattr(
        hc,
        "SafeDnsPinningBackend",
        lambda: (_ for _ in ()).throw(TypeError("incompatible SyncBackend")),
    )
    with pytest.raises(MediaSecurityError) as dep_exc:
        hc._build_pinned_transport()
    assert dep_exc.value.error_code == "ssrf_pinning_unavailable"
