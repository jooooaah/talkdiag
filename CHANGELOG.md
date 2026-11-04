# Changelog

## 0.1.2

- Expand `top` with VideoRoom role, ICE/DTLS state, incoming/outgoing audio/video rates, available RTT and summary totals.
- Add ephemeral H1/H2 handle labels, avoiding sensitive identifiers in live output.
- Add an in-process temporal media-stall heuristic that only follows previously active, negotiated media flows.
- Fix misleading `Complete: False` output by reporting complete/partial based on scan coverage and errors.
- Document metric limits and temporal-alert false positives; add live-mode regression tests.

## 0.1.1

- Parse Janus VideoRoom `plugin_specific.streams` separately from `webrtc.media`.
- Report ICE/DTLS state, media directions, codecs, traffic counters and RTCP values from Janus 1.x handle information.
- Avoid interpreting RTP/RTCP counters as packet-loss percentages.
- Redact selected ICE candidate pair by default.
- Add regression tests for nested Janus Admin API responses.
- Rewrite README in English, using deployment-neutral examples and explicit privacy guidance.

## 0.1.0

- Initial experimental read-only CLI with Janus Admin API, basic diagnostics, optional component checks, browser-side guidance and terminal live view.
