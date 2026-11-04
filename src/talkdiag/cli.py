"""Read-only CLI: no changes to Janus, coturn or system state."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time
from . import __version__
from .config import load_config, Config
from .janus import Janus, JanusError
from .diagnosis import findings, flatten_stream_state, network_group_note
from .components import coturn_cli, signaling_metrics, recording_status


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="talkdiag", description="Read-only Nextcloud Talk server-side diagnostics")
    p.add_argument("--config", help="TOML config path (default: ./config.toml)")
    p.add_argument("--json", action="store_true", help="Output JSON for scripts/support reports")
    p.add_argument("--show-sensitive", action="store_true", help="Include potentially sensitive IDs, IPs, raw payloads in output")
    p.add_argument("--version", action="version", version=f"talkdiag {__version__}")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Component reachability and configuration status")
    commands.add_parser("sessions", help="List Janus sessions and handle counts")
    inspect = commands.add_parser("inspect", help="Inspect one Janus session and handle")
    inspect.add_argument("--session", type=int, required=True)
    inspect.add_argument("--handle", type=int, required=True)
    inspect.add_argument("--raw", action="store_true", help="Include raw Janus response (requires --show-sensitive)")
    scan = commands.add_parser("scan", help="Scan current Janus handles and findings")
    scan.add_argument("--max-handles", type=int, help="Limit API requests per invocation")
    top = commands.add_parser("top", help="Live textual snapshot (Ctrl+C to exit)")
    top.add_argument("--interval", type=float, default=3.0, help="Refresh interval in seconds (minimum 1)")
    top.add_argument("--max-handles", type=int, help="Max handles per refresh")
    browser = commands.add_parser("client-help", help="Instructions to request browser-side WebRTC diagnostics")
    browser.add_argument("--browser", choices=["firefox", "chrome", "edge"], required=True)
    browser.add_argument("--issue", choices=["ice", "media", "signaling"], default="ice")
    commands.add_parser("demo", help="Run against bundled simulated sample; no connection needed")
    return p


def safe(value, allow_sensitive: bool = False):
    """Conservatively remove free-form fields that may hold IPs, SDP and user IDs."""
    if allow_sensitive:
        return value
    if isinstance(value, list):
        return [safe(v, False) for v in value]
    if isinstance(value, dict):
        sensitive = {"remote_ip", "opaque_id", "selected_pair", "selected-pair", "ps_output", "raw", "sdps", "plugin_specific"}
        return {key: ("[redacted]" if key in sensitive and val not in (None, "") else safe(val, False))
                for key, val in value.items()}
    return value


def handle_summary(session: int, handle: int, info: dict, show_sensitive: bool = False) -> dict:
    parsed = flatten_stream_state(info)
    return {"session": session if show_sensitive else "[redacted]", "handle": handle if show_sensitive else "[redacted]",
            "plugin": parsed["plugin"], "opaque_id": parsed["opaque_id"] if show_sensitive else "[redacted]",
            "stream_count": parsed["stream_count"], "streams": safe(parsed["streams"], show_sensitive),
            "plugin_type": parsed["plugin_type"], "plugin_stream_count": parsed["plugin_stream_count"],
            "plugin_streams": safe(parsed["plugin_streams"], show_sensitive),
            "ice": safe(parsed["ice"], show_sensitive), "dtls": parsed["dtls"], "flags": parsed["flags"],
            "queued_packets": parsed["queued_packets"], "findings": findings(info)}


def scan_janus(janus: Janus, limit: int, sensitive: bool) -> dict:
    if limit < 1:
        raise ValueError("max-handles must be positive")
    sessions = janus.sessions()
    result = {"session_count": len(sessions), "handles_scanned": 0, "truncated": False, "handles": [], "errors": []}
    for sid in sessions:
        try:
            handles = janus.handles(sid)
        except JanusError as exc:
            result["errors"].append({"session": sid if sensitive else "[redacted]", "error": str(exc)})
            continue
        for hid in handles:
            if result["handles_scanned"] >= limit:
                result["truncated"] = True
                return result
            result["handles_scanned"] += 1
            try:
                info = janus.handle_info(sid, hid)
                result["handles"].append(handle_summary(sid, hid, info, sensitive))
            except JanusError as exc:
                result["errors"].append({"handle": hid if sensitive else "[redacted]", "error": str(exc)})
    return result


def browser_help(browser: str, issue: str) -> dict:
    page = {"firefox": "about:webrtc", "chrome": "chrome://webrtc-internals", "edge": "edge://webrtc-internals"}[browser]
    checks = {
        "ice": ["Find the PeerConnection for the active Talk tab (there may be several).", "Inspect selected ICE candidate pair: candidate type, protocol, state and RTT.", "Check ICE restarts/disconnects during the incident."],
        "media": ["Inspect inbound-rtp and outbound-rtp for the affected audio/video track.", "Check packetsReceived/packetsSent, packetsLost, jitter and decoded frames where available.", "Compare timestamps with the server-side incident."],
        "signaling": ["Open DevTools (F12), Network, and inspect WebSocket connections.", "Look for repeated disconnects, failed requests and error messages.", "Note the exact timestamp and anonymized error text."],
    }
    return {"browser": browser, "page": page, "issue": issue, "steps": [
        "Keep the affected Talk call open if possible.", f"Open {page} in a separate browser tab." if issue != "signaling" else "Open the affected Talk tab and developer tools (F12).",
        *checks[issue], "Do NOT share raw reports publicly: they can contain client IPs, device details or tokens."],
        "note": "Browser reports do not automatically identify a Talk participant; match by incident time and PeerConnection."}


def demo_data() -> dict:
    example = {"plugin": "janus.plugin.videoroom", "opaque_id": "sample-user", "queued-packets": 160,
               "streams": [{"type": "video", "ice": "disconnected", "dtls": "connected"}]}
    return {"sample": True, "data_source": "SIMULATED - not server measurements",
            "component_status": {"janus": "simulated", "coturn": "simulated"},
            "handle": handle_summary(1234, 5678, example), "network_note": network_group_note()}


def emit(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                print(f"{key}:")
                print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
            else:
                print(f"{key}: {value}")
    else:
        print(data)


def one_shot(args: argparse.Namespace, cfg: Config):
    janus = Janus(cfg)
    if args.command == "demo":
        return demo_data()
    if args.command == "client-help":
        return browser_help(args.browser, args.issue)
    if args.command == "status":
        try:
            janus.call("ping")
            janus_status = {"status": "reachable", "note": "Admin API ping only; media health not established"}
        except JanusError as exc:
            janus_status = {"status": "error", "error": str(exc)}
        return {"observed_at": datetime.now(timezone.utc).isoformat(), "janus": janus_status,
                "coturn": safe(coturn_cli(cfg), args.show_sensitive), "signaling": signaling_metrics(cfg),
                "recording": recording_status(cfg),
                "note": "not_configured and unknown do not mean healthy"}
    if args.command == "sessions":
        sessions = janus.sessions()
        rows = []
        for sid in sessions:
            try:
                num = len(janus.handles(sid))
                rows.append({"session": sid if args.show_sensitive else "[redacted]", "handle_count": num})
            except JanusError as exc:
                rows.append({"session": sid if args.show_sensitive else "[redacted]", "error": str(exc)})
        return {"session_count": len(sessions), "sessions": rows,
                "note": "Janus sessions are not Nextcloud Talk rooms or unique participants."}
    if args.command == "inspect":
        if args.raw and not args.show_sensitive:
            raise ValueError("--raw requires --show-sensitive")
        info = janus.handle_info(args.session, args.handle)
        result = handle_summary(args.session, args.handle, info, args.show_sensitive)
        if args.raw:
            result["raw"] = info
        return result
    if args.command in {"scan", "top"}:
        return scan_janus(janus, args.max_handles or cfg.max_handles, args.show_sensitive)
    raise ValueError("Unsupported command")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        # demo and client-help can run offline, no config required.
        cfg = Config() if args.command in {"demo", "client-help"} else load_config(args.config)
        if args.command == "top":
            if args.interval < 1:
                raise ValueError("interval must be >= 1 second")
            if not sys.stdout.isatty():
                raise ValueError("top requires a terminal; use scan --json for logs")
            try:
                while True:
                    data = one_shot(args, cfg)
                    print("\033[2J\033[H", end="")
                    print("talkdiag 0.1 - LIVE Janus handles | Ctrl+C to exit")
                    print("Janus sessions:", data["session_count"], "Handles scanned:", data["handles_scanned"],
                          "Partial:" if data["truncated"] else "Complete:", data["truncated"])
                    print("-" * 78)
                    print(f"{'HANDLE':<18} {'PLUGIN':<30} {'STREAMS':>7} {'WARN':>5}")
                    for item in data["handles"]:
                        print(f"{str(item['handle']):<18.18} {str(item['plugin']):<30.30} {item['stream_count']:>7} {len(item['findings']):>5}")
                    for error in data["errors"][:5]:
                        print("ERROR", error)
                    print("\nIDs are redacted by default; --show-sensitive reveals them. This is not a participant list.")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped")
                return 0
        else:
            emit(one_shot(args, cfg), args.json)
        return 0
    except (JanusError, OSError, ValueError, KeyError) as exc:
        if args.json:
            emit({"status": "error", "error": str(exc)}, True)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
