"""In-process, conservative live-media diagnostics and plain terminal rendering.

No client identity inference, no persistent collection, and no loss percentages.
"""
from __future__ import annotations
from dataclasses import dataclass, field


def _bitrate(stream: dict, direction: str) -> float | None:
    value = stream.get(direction, {}).get("bytes_lastsec")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return value * 8 / 1000
    return None


def rate_label(kbps: float | None) -> str:
    if kbps is None:
        return "--"
    return f"{kbps / 1000:.1f}M" if kbps >= 1000 else f"{kbps:.0f}k"


def rates(handle: dict, kind: str) -> tuple[float | None, float | None]:
    found = [s for s in handle.get("streams", []) if s.get("type") == kind]
    def total(direction: str):
        nums = [_bitrate(s, direction) for s in found]
        known = [v for v in nums if v is not None]
        return sum(known) if known else None
    return total("in"), total("out")


def rtt_ms(handle: dict) -> int | float | None:
    vals = [s.get("rtcp", {}).get("rtt") for s in handle.get("streams", []) if s.get("type") in ("audio", "video")]
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0]
    return max(vals) if vals else None


@dataclass
class _Flow:
    had_traffic: bool = False
    silent_samples: int = 0
    first_seen: int = 0
    last_seen: int = 0


@dataclass
class LiveAnalyzer:
    """Raises MEDIA_FLOW_STOPPED only after a previously active flow stops.

    Samples are consecutive completed top polls; the rule does not diagnose
    deliberate media pauses or tell us where delivery ceased. State resets when
    a handle/stream disappears or ICE/DTLS is not ready.
    """
    zero_samples: int = 3
    generation: int = 0
    flows: dict[tuple, _Flow] = field(default_factory=dict)

    def update(self, snapshot: dict) -> dict:
        self.generation += 1
        if snapshot.get("errors") or snapshot.get("truncated"):
            # Avoid drawing conclusions from incomplete or failing polls.
            self.flows.clear()
            return snapshot
        seen = set()
        for handle in snapshot.get("handles", []):
            # Internal non-redacted correlation key must never be emitted.
            identity = handle.get("_tracking_key")
            handle["live_findings"] = []
            if not identity:
                continue
            ice = handle.get("ice", {}).get("state")
            dtls = handle.get("dtls", {}).get("state")
            if ice not in ("connected", "ready") or dtls != "connected" or not handle.get("flags", {}).get("negotiated"):
                continue
            for stream in handle.get("streams", []):
                if stream.get("type") not in ("audio", "video"):
                    continue
                direction = stream.get("direction", {})
                for flow_direction, negotiated in (("in", direction.get("recv")), ("out", direction.get("send"))):
                    if negotiated is not True:
                        continue
                    kbps = _bitrate(stream, flow_direction)
                    if kbps is None:
                        continue
                    key = (identity, str(stream.get("mindex")), flow_direction)
                    seen.add(key)
                    state = self.flows.setdefault(key, _Flow(first_seen=self.generation))
                    state.last_seen = self.generation
                    if kbps > 0:
                        state.had_traffic = True
                        state.silent_samples = 0
                    elif state.had_traffic:
                        state.silent_samples += 1
                        if state.silent_samples >= self.zero_samples:
                            handle["live_findings"].append({
                                "severity": "warning", "code": "MEDIA_FLOW_STOPPED",
                                "evidence": f"{stream.get('type')} {flow_direction}: zero bytes_lastsec for {self.zero_samples} consecutive polls after previously observed traffic",
                                "advice": "Inspect intentional mute/pause, subscription state and RTP path; cause is not established.",
                            })
        self.flows = {k: v for k, v in self.flows.items() if k in seen}
        return snapshot


def render_top(snapshot: dict, labels: dict[tuple, str] | None = None) -> str:
    """Pure text snapshot; labels may map internal IDs to short per-process names."""
    labels = labels or {}
    rows = snapshot.get("handles", [])
    complete = not snapshot.get("truncated") and not snapshot.get("errors")
    lines = ["talkdiag - LIVE Janus diagnostics | Ctrl+C to exit",
             f"Sessions: {snapshot.get('session_count', 0)}  Handles: {snapshot.get('handles_scanned', 0)}  Scan: {'complete' if complete else 'partial'}",
             "Rates: kbit/s (k), Mbit/s (M), IN/OUT from Janus; -- = unavailable",
             "-" * 124,
             f"{'HANDLE':<12} {'ROLE':<11} {'ICE':<12} {'DTLS':<12} {'AUDIO IN/OUT':<15} {'VIDEO IN/OUT':<15} {'RTT':>7} {'R-CAND':<14} {'WARN':>4}"]
    total_in = total_out = 0.0
    known_rates = False
    for idx, handle in enumerate(rows, 1):
        identity = handle.get("_tracking_key")
        label = labels.get(identity, f"H{idx}")
        role = handle.get("plugin_type") or "unknown"
        ice = handle.get("ice", {}).get("state") or "--"
        dtls = handle.get("dtls", {}).get("state") or "--"
        a_in, a_out = rates(handle, "audio")
        v_in, v_out = rates(handle, "video")
        for value in (a_in, a_out, v_in, v_out):
            if value is not None:
                known_rates = True
        total_in += (a_in or 0) + (v_in or 0)
        total_out += (a_out or 0) + (v_out or 0)
        rtt = rtt_ms(handle)
        warn = len(handle.get("findings", [])) + len(handle.get("live_findings", []))
        inventory = handle.get("network", {}).get("remote_candidates", {})
        types = inventory.get("types", {})
        r_cand = ",".join(f"{k}:{types[k]}" for k in sorted(types)) if inventory.get("available") else "--"
        if inventory.get("available") and not types:
            r_cand = "none/unknown"
        lines.append(f"{str(label):<12.12} {str(role):<11.11} {str(ice):<12.12} {str(dtls):<12.12} "
                     f"{(rate_label(a_in)+'/'+rate_label(a_out)):<15} {(rate_label(v_in)+'/'+rate_label(v_out)):<15} "
                     f"{(str(rtt)+'ms') if rtt is not None else '--':>7} {r_cand:<14.14} {warn:>4}")
    lines.extend(["-" * 124,
                  f"Observed media totals: IN {rate_label(total_in) if known_rates else '--'}  OUT {rate_label(total_out) if known_rates else '--'} (known streams only; no double counting data channels)"])
    for handle in rows:
        identity = handle.get("_tracking_key")
        for finding in (handle.get("findings", []) + handle.get("live_findings", [])):
            lines.append(f"! {labels.get(identity, 'handle')}: {finding['code']} — {finding['evidence']}")
    for error in snapshot.get("errors", [])[:5]:
        lines.append(f"ERROR: {error}")
    lines.append("R-CAND = available remote candidate types, NOT the selected ICE route. No client identity inference.")
    lines.append("Short labels are local to this live run, not participant IDs.")
    return "\n".join(lines)
