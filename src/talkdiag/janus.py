"""Only read-only Janus Admin/Monitor API commands are exposed."""
from __future__ import annotations
import json
import secrets
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .config import Config

class JanusError(RuntimeError):
    pass

class Janus:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if not cfg.janus_url.startswith(("http://", "https://")):
            raise JanusError("Janus URL must be http(s)")

    def call(self, action: str, session: int | None = None, handle: int | None = None) -> dict:
        if action not in {"ping", "info", "get_status", "list_sessions", "list_handles", "handle_info"}:
            raise JanusError(f"Disallowed API action: {action}")
        payload: dict = {"janus": action, "transaction": secrets.token_hex(8)}
        if self.cfg.janus_secret:
            payload["admin_secret"] = self.cfg.janus_secret
        url = self.cfg.janus_url.rstrip("/")
        if session is not None:
            payload["session_id"] = int(session)
            url += f"/{int(session)}"
        if handle is not None:
            payload["handle_id"] = int(handle)
            url += f"/{int(handle)}"
        req = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.cfg.timeout) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            raise JanusError(f"Janus admin request failed ({action}): {type(exc).__name__}: {exc}") from None
        if not isinstance(result, dict):
            raise JanusError("Unexpected non-object Janus response")
        if result.get("janus") == "error":
            error = result.get("error", {})
            raise JanusError(f"Janus error {error.get('code', '?')}: {error.get('reason', 'unknown')}")
        if result.get("janus") not in {"success", "pong", "server_info", "ack"}:
            raise JanusError(f"Unexpected Janus response kind: {result.get('janus')}")
        return result

    def sessions(self) -> list[int]:
        return [int(x) for x in self.call("list_sessions").get("sessions", [])]

    def handles(self, session: int) -> list[int]:
        return [int(x) for x in self.call("list_handles", session=session).get("handles", [])]

    def handle_info(self, session: int, handle: int) -> dict:
        info = self.call("handle_info", session=session, handle=handle).get("info", {})
        if not isinstance(info, dict):
            raise JanusError("Unexpected handle_info payload")
        return info
