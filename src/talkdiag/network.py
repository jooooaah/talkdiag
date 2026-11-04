"""Privacy-preserving ICE candidate inventories, not client identity attribution.

Janus may expose only foundations for selected-pair, and candidate lists do not
prove which candidate was selected. Never infer a firewall restriction from
candidate availability alone.
"""
from __future__ import annotations
import re

TYPES = ("host", "srflx", "prflx", "relay")
PROTOCOLS = ("udp", "tcp")


def _one(candidate) -> tuple[str | None, str | None]:
    if isinstance(candidate, dict):
        kind = candidate.get("type") or candidate.get("candidate_type") or candidate.get("candidate-type")
        proto = candidate.get("protocol") or candidate.get("transport")
        kind = kind.lower() if isinstance(kind, str) else None
        proto = proto.lower() if isinstance(proto, str) else None
    elif isinstance(candidate, str):
        # SDP candidates: candidate:<foundation> <component> <protocol> ... typ <type>
        kind_match = re.search(r"\btyp\s+(host|srflx|prflx|relay)\b", candidate, re.I)
        proto_match = re.search(r"(?:^|\s)(?:\S+\s+)?(?:\d+\s+)(udp|tcp)\s+\d+", candidate, re.I)
        kind = kind_match.group(1).lower() if kind_match else None
        proto = proto_match.group(1).lower() if proto_match else None
        if proto is None:
            match = re.search(r"\b(?:protocol|transport)\s*[=:]\s*(udp|tcp)\b", candidate, re.I)
            proto = match.group(1).lower() if match else None
    else:
        return None, None
    return kind if kind in TYPES else None, proto if proto in PROTOCOLS else None


def summarize_candidates(value) -> dict:
    if not isinstance(value, list):
        return {"available": False, "count": None, "types": {}, "protocols": {}, "unclassified": None}
    types: dict[str, int] = {}
    protocols: dict[str, int] = {}
    unknown = 0
    for candidate in value:
        kind, proto = _one(candidate)
        if kind:
            types[kind] = types.get(kind, 0) + 1
        if proto:
            protocols[proto] = protocols.get(proto, 0) + 1
        if not kind or not proto:
            unknown += 1
    return {"available": True, "count": len(value), "types": types,
            "protocols": protocols, "unclassified": unknown}


def ice_network(ice: dict) -> dict:
    raw_pair = ice.get("selected-pair")
    return {
        "local_candidates": summarize_candidates(ice.get("local-candidates")),
        "remote_candidates": summarize_candidates(ice.get("remote-candidates")),
        "selected_pair_observed": isinstance(raw_pair, str) and bool(raw_pair.strip()),
        "selected_path": "unverified",
        "note": ("Candidate lists describe available candidates, not the selected route. "
                 "Janus selected-pair may contain foundations only. Remote relay candidates "
                 "do not prove a TCP fallback or a client firewall issue."),
    }
