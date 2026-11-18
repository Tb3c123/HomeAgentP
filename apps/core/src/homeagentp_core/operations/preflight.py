"""Offline, report-only Docker Compose configuration preflight (Phase 06).

Accepts an already-exported Compose JSON document; this module never invokes Docker,
executes shell commands, reads secrets or touches running containers.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_SERVICE_NAMES = frozenset({"homeagentp-core", "homeagentp-web"})
FORBIDDEN_MOUNT_SOURCES = ("/var/run/docker.sock", "/mnt/disk1", "/mnt/disk2", "/root", "/")
DRAFT_IMAGE_MARKERS = (":0.1.0-draft", ":latest")
ALLOWED_READONLY_BIND_ROOTS = ("/opt/homeagentp/config", "/var/lib/homeagentp/reports")
IMAGE_DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[a-fA-F0-9]{64}$")


def check_compose_document(document: object) -> dict[str, Any]:
    """Produce bounded, secret-free findings from a decoded Docker Compose JSON document."""
    findings: list[dict[str, str]] = []

    def add(check: str, status: str, detail: str) -> None:
        findings.append({"check": check, "status": status, "detail": detail})

    if not isinstance(document, dict):
        add("compose_schema", "FAIL", "Compose root must be an object.")
        return {"status": "FAIL", "evidence_scope": "offline_config", "findings": findings}
    services = document.get("services")
    if not isinstance(services, dict):
        add("compose_services", "FAIL", "Compose services mapping is missing.")
        return {"status": "FAIL", "evidence_scope": "offline_config", "findings": findings}

    for _unexpected_name in sorted(set(services) - ALLOWED_SERVICE_NAMES):
        add("compose.extra_service", "FAIL", "Unexpected service in Compose definition.")

    for name in sorted(ALLOWED_SERVICE_NAMES):
        service = services.get(name)
        if not isinstance(service, dict):
            add(f"{name}.present", "FAIL", "Required service missing.")
            continue
        user = service.get("user")
        expected_user = "10001:10001" if name == "homeagentp-core" else "101:101"
        add(f"{name}.user", "PASS" if str(user) == expected_user else "FAIL",
            "Expected fixed non-root UID:GID.")
        add(f"{name}.readonly", "PASS" if service.get("read_only") is True else "FAIL",
            "Root filesystem must be read-only.")
        add(f"{name}.privileged", "PASS" if service.get("privileged") is not True else "FAIL",
            "Privileged mode must be disabled.")
        add(f"{name}.network", "PASS" if service.get("network_mode") != "host" else "FAIL",
            "Host networking must be disabled.")
        caps = service.get("cap_drop")
        add(f"{name}.cap_drop", "PASS" if isinstance(caps, list) and "ALL" in caps else "FAIL",
            "All Linux capabilities must be dropped.")
        opts = service.get("security_opt")
        add(f"{name}.no_new_privileges",
            "PASS" if isinstance(opts, list) and any(
                str(x).lower() in ("no-new-privileges:true", "no-new-privileges=true")
                for x in opts
            ) else "FAIL",
            "No-new-privileges must be enabled.")

        mounts = service.get("volumes", [])
        if not isinstance(mounts, list):
            mounts = []
            add(f"{name}.mount_schema", "FAIL", "Volumes must be a list.")
        for i, mount in enumerate(mounts[:50]):
            if isinstance(mount, dict):
                mount_type = mount.get("type")
                src = str(mount.get("source", ""))
                dst = str(mount.get("target", ""))
                read_only = mount.get("read_only") is True
            elif isinstance(mount, str):
                pieces = mount.split(":")
                mount_type = "bind" if pieces and pieces[0].startswith("/") else "volume"
                src = pieces[0]
                dst = pieces[1] if len(pieces) > 1 else ""
                read_only = "ro" in pieces[2:]
            else:
                add(f"{name}.mount.{i}", "FAIL", "Invalid mount structure.")
                continue
            forbidden = (
                any(src == prefix or src.startswith(prefix + "/")
                    for prefix in FORBIDDEN_MOUNT_SOURCES)
                or any(dst == prefix or dst.startswith(prefix + "/")
                       for prefix in ("/var/run/docker.sock", "/host", "/mnt"))
            )
            unsafe_writable_bind = mount_type == "bind" and not read_only
            allowlisted_bind = (
                mount_type != "bind"
                or (
                    src.startswith("/")
                    and ".." not in src.split("/")
                    and any(
                        src == root or src.startswith(root + "/")
                        for root in ALLOWED_READONLY_BIND_ROOTS
                    )
                )
            )
            add(
                f"{name}.mount.{i}",
                "FAIL" if forbidden or unsafe_writable_bind or not allowlisted_bind else "PASS",
                "Bind mounts must be read-only and use the explicit safe source allowlist.",
            )
        if len(mounts) > 50:
            add(f"{name}.mount_limit", "FAIL", "Too many mounts to inspect.")

        ports = service.get("ports", [])
        if not isinstance(ports, list):
            add(f"{name}.ports", "FAIL", "Ports must be a list.")
        else:
            for i, port in enumerate(ports[:20]):
                if isinstance(port, dict):
                    ip = str(port.get("host_ip", ""))
                else:
                    # Plain strings must use explicit IPv4 localhost prefix.
                    ip = (
                        "127.0.0.1"
                        if isinstance(port, str) and port.startswith("127.0.0.1:")
                        else ""
                    )
                add(f"{name}.port.{i}", "PASS" if ip in ("127.0.0.1", "::1") else "FAIL",
                    "Published ports must bind loopback only.")
            if len(ports) > 20:
                add(f"{name}.port_limit", "FAIL", "Too many ports to inspect.")

        tag = service.get("image")
        if tag is None:
            add(f"{name}.image", "UNKNOWN", "Image provenance requires a pinned release digest.")
        else:
            safe_digest = (
                isinstance(tag, str)
                and IMAGE_DIGEST_RE.fullmatch(tag) is not None
                and not any(marker in tag for marker in DRAFT_IMAGE_MARKERS)
            )
            add(f"{name}.image", "PASS" if safe_digest else "FAIL",
                "Production image must be verified and digest-pinned; draft tags forbidden.")

    statuses = {entry["status"] for entry in findings}
    overall = "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    return {"status": overall, "evidence_scope": "offline_config", "findings": findings}


def main() -> int:
    """Inspect supplied JSON without executing services or disclosing config values."""
    if len(sys.argv) != 2:
        print("Usage: python -m homeagentp_core.operations.preflight COMPOSE_JSON", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        if path.is_symlink() or path.stat().st_size > 262_144:
            raise ValueError("Invalid Compose JSON input size or type.")
        document: object = json.loads(path.read_text(encoding="utf-8"))
        result = check_compose_document(document)
    except (OSError, ValueError):
        result = {"status": "FAIL", "evidence_scope": "offline_config",
                  "findings": [{"check": "input", "status": "FAIL",
                                "detail": "Unable to validate Compose JSON input."}]}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
