"""Conservative interpretations. Never equate relay use with firewall blocking."""
from __future__ import annotations
from collections import Counter


def flatten_stream_state(info: dict) -> dict:
    """Janus stream schemas differ; show known fields and preserve unknowns in raw output."""
    streams = info.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    states = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        states.append({
            "type": stream.get("type", stream.get("media", "?")),
            "ice": stream.get("ice", stream.get("ice-state", "?")),
            "dtls": stream.get("dtls", stream.get("dtls-state", "?")),
            "selected_pair": stream.get("selected-pair", stream.get("selected_pair")),
        })
    return {"plugin": info.get("plugin", "?"), "opaque_id": info.get("opaque_id", ""), "streams": states,
            "queued_packets": info.get("queued-packets"), "stream_count": len(streams)}


def findings(info: dict) -> list[dict]:
    output = []
    queue = info.get("queued-packets")
    if isinstance(queue, (int, float)) and queue > 100:
        output.append({"severity": "warning", "code": "QUEUE_HIGH", "evidence": f"queued-packets={queue}",
                       "advice": "Check Janus load and media delivery; threshold is heuristic."})
    for i, stream in enumerate(info.get("streams", []) if isinstance(info.get("streams"), list) else []):
        if not isinstance(stream, dict):
            continue
        for key in ("ice", "ice-state"):
            state = stream.get(key)
            if isinstance(state, str) and state.lower() in {"failed", "disconnected"}:
                output.append({"severity": "warning", "code": "ICE_UNSTABLE", "evidence": f"stream[{i}].{key}={state}",
                               "advice": "Inspect ICE state and selected candidate pair in browser WebRTC diagnostics."})
                break
    return output


def network_group_note() -> str:
    return ("Network grouping by actual client IP / ASN is NOT implemented in v0.1. "
            "Janus may see a TURN relay address instead of the client source IP. "
            "Never infer a client firewall restriction from TURN use alone.")
