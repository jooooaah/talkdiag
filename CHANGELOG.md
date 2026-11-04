# Changelog

## 0.1.1

- Parse Janus VideoRoom `plugin_specific.streams` separately from `webrtc.media`.
- Report ICE/DTLS state, media directions, codecs, traffic counters and RTCP values from Janus 1.x handle information.
- Avoid interpreting RTP/RTCP counters as packet-loss percentages.
- Redact selected ICE candidate pair by default.
- Add regression tests for nested Janus Admin API responses.
- Rewrite README in English, using deployment-neutral examples and explicit privacy guidance.

## 0.1.0

- Initial experimental read-only CLI with Janus Admin API, basic diagnostics, optional component checks, browser-side guidance and terminal live view.
