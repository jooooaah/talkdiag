"""Conservative interpretations of Janus Admin API handle_info.

Supported structures include Janus 1.x: plugin_specific.streams and
webrtc.media (a dictionary keyed by m-line index). Values are observations,
not proof of a client-side or server-side root cause.
"""
from __future__ import annotations
from .network import ice_network


def _object(value):
    return value if isinstance(value, dict) else {}


def _value(value):
    return value if isinstance(value, (str, int, float, bool)) else None


def _media_items(media):
    if isinstance(media, dict):
        return sorted(((str(k), v) for k, v in media.items() if isinstance(v, dict)),
                      key=lambda kv: (not kv[0].isdigit(), int(kv[0]) if kv[0].isdigit() else kv[0]))
    if isinstance(media, list):
        return [(str(i), v) for i, v in enumerate(media) if isinstance(v, dict)]
    return []


def _media_summary(index: str, medium: dict) -> dict:
    stats = _object(medium.get("stats"))
    rtcp = _object(_object(medium.get("rtcp")).get("main"))
    direction = _object(medium.get("direction"))
    inbound, outbound = _object(stats.get("in")), _object(stats.get("out"))
    return {
        "mindex": _value(medium.get("mindex")) if medium.get("mindex") is not None else index,
        "mid": _value(medium.get("mid")),
        "type": _value(medium.get("type")),
        "direction": {"send": _value(direction.get("send")), "recv": _value(direction.get("recv"))},
        "codec": _value(_object(medium.get("codecs")).get("codec")),
        "in": {"packets_total": _value(inbound.get("packets")),
               "bytes_total": _value(inbound.get("bytes")),
               "bytes_lastsec": _value(inbound.get("bytes_lastsec")),
               "nacks_total": _value(inbound.get("nacks")),
               "retransmissions_total": _value(inbound.get("retransmissions"))},
        "out": {"packets_total": _value(outbound.get("packets")),
                "bytes_total": _value(outbound.get("bytes")),
                "bytes_lastsec": _value(outbound.get("bytes_lastsec")),
                "nacks_total": _value(outbound.get("nacks"))},
        "rtcp": {"rtt": _value(rtcp.get("rtt")),
                 "lost_total": _value(rtcp.get("lost")),
                 "lost_by_remote_total": _value(rtcp.get("lost-by-remote")),
                 "jitter_local": _value(rtcp.get("jitter-local")),
                 "jitter_remote": _value(rtcp.get("jitter-remote")),
                 "in_link_quality": _value(rtcp.get("in-link-quality")),
                 "out_link_quality": _value(rtcp.get("out-link-quality"))},
    }


def flatten_stream_state(info: dict) -> dict:
    """Summarize both videoroom plugin streams and WebRTC transport/media stats.

    A missing field is None/unknown, never implicitly healthy. Counters are
    retained as counters, never misrepresented as packet-loss percentages.
    """
    plugin = _object(info.get("plugin_specific"))
    plugin_streams = plugin.get("streams")
    if not isinstance(plugin_streams, list):
        plugin_streams = []
    plugin_items = [
        {"type": _value(s.get("type")), "mid": _value(s.get("mid")),
         "mindex": _value(s.get("mindex")), "codec": _value(s.get("codec")),
         "subscribers": _value(s.get("subscribers"))}
        for s in plugin_streams if isinstance(s, dict)
    ]
    webrtc = _object(info.get("webrtc"))
    ice, dtls = _object(webrtc.get("ice")), _object(webrtc.get("dtls"))
    media = [_media_summary(index, item) for index, item in _media_items(webrtc.get("media"))]
    # The older flat 'streams' schema is retained for compatibility with early test fixtures.
    flat = info.get("streams")
    if not media and not plugin_items and isinstance(flat, list):
        media = [{"type": _value(s.get("type") or s.get("media")),
                  "ice": _value(s.get("ice") or s.get("ice-state")),
                  "dtls": _value(s.get("dtls") or s.get("dtls-state")),
                  "selected_pair": _value(s.get("selected-pair") or s.get("selected_pair"))}
                 for s in flat if isinstance(s, dict)]
    return {
        "plugin": _value(info.get("plugin")) or "unknown",
        "opaque_id": info.get("opaque_id"),
        "plugin_type": _value(plugin.get("type")),
        "plugin_stream_count": len(plugin_items),
        "plugin_streams": plugin_items,
        "stream_count": len(media),
        "streams": media,
        "network": ice_network(ice),
        "ice": {"state": _value(ice.get("state")),
                "selected_pair": ice.get("selected-pair"),
                "ready": _value(ice.get("ready"))},
        "dtls": {"state": _value(dtls.get("dtls-state")),
                 "ready": _value(dtls.get("ready"))},
        "flags": {"ready": _value(_object(info.get("flags")).get("ready")),
                  "negotiated": _value(_object(info.get("flags")).get("negotiated"))},
        "queued_packets": _value(info.get("queued-packets")),
    }


def findings(info: dict) -> list[dict]:
    parsed = flatten_stream_state(info)
    output = []
    queue = parsed["queued_packets"]
    if isinstance(queue, (int, float)) and not isinstance(queue, bool) and queue > 100:
        output.append({"severity": "warning", "code": "QUEUE_HIGH",
                       "evidence": f"queued-packets={queue}",
                       "advice": "Inspect SFU load and media delivery; threshold is heuristic."})
    ice = parsed["ice"]["state"]
    if isinstance(ice, str) and ice.lower() in {"failed", "disconnected"}:
        output.append({"severity": "warning", "code": "ICE_UNSTABLE",
                       "evidence": f"webrtc.ice.state={ice}",
                       "advice": "Inspect candidate-pair changes and client-side ICE diagnostics."})
    dtls = parsed["dtls"]["state"]
    if isinstance(dtls, str) and dtls.lower() in {"failed", "disconnected"}:
        output.append({"severity": "warning", "code": "DTLS_UNSTABLE",
                       "evidence": f"webrtc.dtls.dtls-state={dtls}",
                       "advice": "Inspect WebRTC handshake and signaling events."})
    # Older fixture-only schema
    if not isinstance(ice, str):
        for index, stream in enumerate(parsed["streams"]):
            state = stream.get("ice")
            if isinstance(state, str) and state.lower() in {"failed", "disconnected"}:
                output.append({"severity": "warning", "code": "ICE_UNSTABLE",
                               "evidence": f"streams[{index}].ice={state}",
                               "advice": "Inspect ICE and selected candidate pair on the client."})
    return output


def network_group_note() -> str:
    return ("Client IP/ASN correlation is not implemented. Janus may observe a TURN "
            "relay address rather than the client IP. TURN use alone is not evidence "
            "of client firewall restrictions.")
