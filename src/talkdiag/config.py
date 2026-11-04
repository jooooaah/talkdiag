"""Configuration is TOML (Python 3.11+), secrets supplied by environment variables."""
from __future__ import annotations
import os
from pathlib import Path
import tomllib
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    janus_url: str = "http://127.0.0.1:7088/admin"
    janus_secret: str = ""
    signaling_metrics_url: str = ""
    coturn_host: str = ""
    coturn_port: int = 5766
    coturn_password: str = ""
    recording_unit: str = ""
    timeout: float = 3.0
    max_handles: int = 150


def load_config(path: str | None = None) -> Config:
    location = Path(path or os.getenv("TALKDIAG_CONFIG", "config.toml"))
    data: dict = {}
    if location.exists():
        with location.open("rb") as fh:
            data = tomllib.load(fh)
    elif path is not None or os.getenv("TALKDIAG_CONFIG"):
        raise FileNotFoundError(f"Config not found: {location}")
    janus = data.get("janus", {})
    signal = data.get("signaling", {})
    turn = data.get("coturn", {})
    rec = data.get("recording", {})
    common = data.get("general", {})
    return Config(
        janus_url=os.getenv("TALKDIAG_JANUS_URL", janus.get("admin_url", Config.janus_url)),
        janus_secret=os.getenv("TALKDIAG_JANUS_SECRET", janus.get("admin_secret", "")),
        signaling_metrics_url=signal.get("metrics_url", ""),
        coturn_host=turn.get("cli_host", ""),
        coturn_port=int(turn.get("cli_port", 5766)),
        coturn_password=os.getenv("TALKDIAG_COTURN_PASSWORD", turn.get("cli_password", "")),
        recording_unit=rec.get("systemd_unit", ""),
        timeout=float(common.get("timeout_seconds", 3.0)),
        max_handles=int(common.get("max_handles", 150)),
    )
