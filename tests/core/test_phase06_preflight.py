"""Offline Compose preflight is deterministic and never prints secrets."""

from __future__ import annotations

import copy

from homeagentp_core.operations.preflight import check_compose_document


def _safe_service(user: str) -> dict[str, object]:
    return {
        "user": user,
        "read_only": True,
        "privileged": False,
        "network_mode": "bridge",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "volumes": [{"type": "bind", "source": "/opt/homeagentp/config",
                     "target": "/config", "read_only": True}],
        "ports": [{"host_ip": "127.0.0.1", "published": "18310", "target": 8310}],
        "image": "ghcr.io/example/homeagentp@sha256:" + "a" * 64,
        "environment": {"HOMEAGENTP_SECRET_KEY": "DO_NOT_PRINT_MY_SECRET"},
    }


def _document() -> dict[str, object]:
    return {"services": {
        "homeagentp-core": _safe_service("10001:10001"),
        "homeagentp-web": _safe_service("101:101"),
    }}


def test_preflight_safe_explicit_compose_passes_and_redacts_secrets() -> None:
    result = check_compose_document(_document())
    assert result["status"] == "PASS"
    assert result["evidence_scope"] == "offline_config"
    assert "DO_NOT_PRINT_MY_SECRET" not in str(result)
    assert "ghcr.io/example" not in str(result)


def test_preflight_unsafe_privileges_mounts_exposure_and_draft_fail_closed() -> None:
    doc = _document()
    core = doc["services"]["homeagentp-core"]  # type: ignore[index]
    core["user"] = "0:0"  # type: ignore[index]
    core["privileged"] = True  # type: ignore[index]
    core["volumes"] = [  # type: ignore[index]
        {"type": "bind", "source": "/var/run/docker.sock",
         "target": "/var/run/docker.sock", "read_only": False}
    ]
    core["ports"] = [{"host_ip": "0.0.0.0"  # noqa: S104, "published": 8310}]  # type: ignore[index]
    core["image"] = "ghcr.io/example/homeagentp:0.1.0-draft"  # type: ignore[index]
    result = check_compose_document(doc)
    assert result["status"] == "FAIL"
    failing = {x["check"] for x in result["findings"] if x["status"] == "FAIL"}
    assert {"homeagentp-core.user", "homeagentp-core.privileged",
            "homeagentp-core.mount.0", "homeagentp-core.port.0",
            "homeagentp-core.image"} <= failing


def test_preflight_missing_services_and_image_unknown() -> None:
    assert check_compose_document({"services": {}})["status"] == "FAIL"
    assert check_compose_document(None)["status"] == "FAIL"
    doc = _document()
    web = doc["services"]["homeagentp-web"]  # type: ignore[index]
    del web["image"]  # type: ignore[index]
    result = check_compose_document(doc)
    assert result["status"] == "UNKNOWN"
    assert copy.deepcopy(doc) == doc
