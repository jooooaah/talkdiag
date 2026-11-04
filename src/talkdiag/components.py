"""Optional read-only component checks. Do not claim complete health from reachability."""
from __future__ import annotations
import json
import re
import socket
import subprocess
from urllib.request import urlopen
from urllib.error import URLError
from .config import Config

_METRIC = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+(-?[0-9]+(?:\.[0-9]+)?)")

def signaling_metrics(cfg: Config) -> dict:
    if not cfg.signaling_metrics_url:
        return {"status": "not_configured"}
    try:
        with urlopen(cfg.signaling_metrics_url, timeout=cfg.timeout) as response:
            content = response.read(2_000_000).decode("utf-8", "replace")
        keep = {"signaling_proxy_sessions", "signaling_proxy_publishers", "signaling_proxy_subscribers", "signaling_backend_current"}
        counters: dict[str, float] = {}
        for line in content.splitlines():
            match = _METRIC.match(line)
            if match and match.group(1) in keep:
                counters[match.group(1)] = counters.get(match.group(1), 0) + float(match.group(2))
        return {"status": "reachable", "metrics": counters,
                "note": "Only selected metrics; no per-participant correlation."}
    except (OSError, URLError, TimeoutError) as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def recording_status(cfg: Config) -> dict:
    if not cfg.recording_unit:
        return {"status": "not_configured"}
    # No shell; strict single unit argument.
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", cfg.recording_unit):
        return {"status": "error", "error": "Invalid systemd unit name"}
    try:
        res = subprocess.run(["systemctl", "is-active", cfg.recording_unit], text=True, capture_output=True,
                             timeout=cfg.timeout, check=False)
        return {"status": "active" if res.stdout.strip() == "active" else "inactive",
                "unit": cfg.recording_unit, "systemd_state": res.stdout.strip() or res.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}


def coturn_cli(cfg: Config) -> dict:
    """Best-effort coturn management CLI: local network only; read-only 'ps' command."""
    if not cfg.coturn_host:
        return {"status": "not_configured"}
    # Avoid accidentally connecting the plaintext management protocol across an external network.
    if cfg.coturn_host not in {"127.0.0.1", "::1", "localhost"}:
        return {"status": "error", "error": "coturn CLI is restricted to loopback; use SSH tunnel"}
    try:
        with socket.create_connection((cfg.coturn_host, cfg.coturn_port), timeout=cfg.timeout) as s:
            s.settimeout(cfg.timeout)
            initial = _read_until_quiet(s)
            if "password" in initial.lower():
                if not cfg.coturn_password:
                    return {"status": "auth_required"}
                s.sendall(cfg.coturn_password.encode() + b"\n")
                initial = _read_until_quiet(s)
                if "wrong" in initial.lower() or "invalid" in initial.lower():
                    return {"status": "auth_failed"}
            s.sendall(b"ps\n")
            raw = _read_until_quiet(s, max_bytes=128_000)
        # Session text has version-dependent structure, so no brittle session parsing.
        return {"status": "reachable", "ps_output": raw.strip(),
                "note": "Raw coturn ps output; no authenticated per-client correlation."}
    except (OSError, TimeoutError) as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _read_until_quiet(sock: socket.socket, max_bytes: int = 4096) -> str:
    chunks = []
    total = 0
    # Short bounded read: banners and CLI prompts vary by coturn version.
    sock.settimeout(0.35)
    for _ in range(16):
        try:
            chunk = sock.recv(min(4096, max_bytes - total))
        except socket.timeout:
            break
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total >= max_bytes:
            break
    return b"".join(chunks).decode("utf-8", "replace")
