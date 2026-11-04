# talkdiag 0.1.3 — Nextcloud Talk Server Diagnostics

**Experimental, read-only command-line troubleshooting for Nextcloud Talk media infrastructure.** The first release focuses on Janus Admin/Monitor API observations; optional adapters provide limited coturn, Signaling and recording status. This tool is **not** a replacement for Prometheus/Grafana.

Python **3.11+**, with **no required third-party runtime dependencies**. Includes text output, JSON output suitable for diagnostic logs, and a simple terminal live view.

> **Scope and limits:** Janus sessions/handles are **not** Nextcloud Talk rooms or uniquely identified people. A TURN relay address is not necessarily a client's public address. No client-firewall conclusions are made from TURN use alone. Missing observations are **unknown**, not healthy.

## Quick installation (Linux)

```bash
sudo apt-get install -y python3 python3-venv unzip  # Debian/Ubuntu example
unzip talkdiag-v0.1.3.zip
cd talkdiag-repo
python3 -m venv .venv
cp config.example.toml config.toml
chmod 600 config.toml
./bin/talkdiag demo
./bin/talkdiag --help
```

The bundled `./bin/talkdiag` launcher runs the sources in the repository with the local virtual environment. **No `pip install` is necessary.** Alternatively, run `PYTHONPATH=src python3 -m talkdiag ...`.

For an existing installation, apply the *patch archive* in the repository root instead; see [Patch upgrades](#patch-upgrades).

## Janus Admin/Monitor API

`talkdiag` requires the **Janus Admin API**, not the normal public Janus API. Configure the endpoint using your deployment system (package configuration, configuration management, or container orchestration); do not make manual changes to managed files that will be overwritten on the next deployment.

Typical endpoint: `http://127.0.0.1:7088/admin`. A Janus HTTP transport configuration might contain:

```ini
# Illustrative only; adapt to the installed Janus release and network setup.
general: {
    http = false
    https = false
}
admin: {
    admin_http = true
    admin_port = 7088
    admin_base_path = "/admin"
    admin_https = false
}
```

**Security requirements:** Keep the Admin API on a protected interface/network, never expose port 7088 to the internet or a public reverse proxy, configure a strong and separate Janus `admin_secret` in the main Janus configuration, and restrict access at the network layer as appropriate. The Admin API itself can execute mutating operations even though `talkdiag` only sends read-only requests.

A containerized deployment can run the CLI in a **separate diagnostic container attached only to an authorized internal network**, using its service DNS name (for example `http://janus:7088/admin`). **Do not mount the Docker socket** in that container. A host-based installation can use a reachable private endpoint or a protected tunnel. Avoid hardcoding container IP addresses that can change after redeployment.

In `config.toml`:

```toml
[general]
timeout_seconds = 3
max_handles = 150

[janus]
admin_url = "http://127.0.0.1:7088/admin"  # replace with your protected endpoint
```

Read the secret interactively rather than putting it in command history or the repository:

```bash
read -rs -p 'Janus Admin Secret: ' TALKDIAG_JANUS_SECRET; echo
export TALKDIAG_JANUS_SECRET
./bin/talkdiag sessions
unset TALKDIAG_JANUS_SECRET
```

The secret is included as `admin_secret` in the JSON body of Janus Admin API requests. **`status` uses an API ping that does not establish authorization for privileged read requests**; verify with `sessions` or `scan` too. Janus may return an application error in an HTTP 200 body.

## Commands

All global flags (`--json`, `--config`, `--show-sensitive`) precede the subcommand:

```bash
./bin/talkdiag status
./bin/talkdiag sessions
./bin/talkdiag scan
./bin/talkdiag paths
./bin/talkdiag --json paths > paths.json
./bin/talkdiag top --interval 3
./bin/talkdiag --json scan > diagnosis.json
./bin/talkdiag --show-sensitive sessions
./bin/talkdiag --show-sensitive inspect --session 1234 --handle 5678
./bin/talkdiag --json --show-sensitive inspect --session 1234 --handle 5678 --raw > handle.json
./bin/talkdiag client-help --browser firefox --issue ice
./bin/talkdiag client-help --browser chrome --issue media
./bin/talkdiag demo
```

`top` requires an interactive terminal. Use `--json scan` for machine-readable snapshots; all JSON errors are returned as JSON with a non-zero process exit code. **If you redirect to a file, verify it with** `python3 -m json.tool diagnosis.json >/dev/null` **before processing it as JSON.**

## What is reported

Version 0.1.3 reads the following Janus `handle_info` structures when available:

- `plugin_specific.streams`: VideoRoom stream descriptors, codec and subscriber counts.
- `webrtc.ice`: ICE connection state, selected candidate pair (pair redacted by default), and privacy-preserving counts/types/protocols of local/remote candidate inventories.
- `webrtc.dtls`: DTLS state and readiness.
- `webrtc.media`: per-m-line audio/video direction, codec, RTP packet/byte totals, `bytes_lastsec`, NACK and retransmission counters, and RTCP values including RTT, jitter and loss counters.
- `queued-packets` and basic handle readiness flags.

The `stream_count` in a handle summary represents **WebRTC media entries**, not a number of subscribers or people. `plugin_stream_count` is shown separately. RTP/RTCP packet-loss fields are **raw counters, not loss percentages**; `bytes_lastsec` is the field reported by Janus, not a smoothed bitrate. A single sample is insufficient to prove media stalling or explain an ICE fallback.

Single-snapshot findings are intentionally conservative: `QUEUE_HIGH`, `ICE_UNSTABLE`, and `DTLS_UNSTABLE` based on explicitly observed conditions. The lack of a finding does not establish a healthy stream.

## ICE network diagnostics (`paths`) — version 0.1.3

Run `./bin/talkdiag paths` or `./bin/talkdiag --json paths` to inspect the available ICE candidates per Janus handle. Output includes totals by candidate **type** (`host`, `srflx`, `prflx`, `relay`) and advertised **protocol** (`udp`, `tcp`) for both local and remote inventories, plus an `unclassified` count. **Candidate addresses, ports, and raw candidate lines are not included**, even with `--show-sensitive` (that flag does expose session/handle IDs; `inspect --raw` can expose full sensitive ICE and SDP values). Missing candidate arrays are reported as unavailable, distinct from an available empty array.

Crucially, these are **available candidates, not necessarily the selected candidate pair**. Janus may expose `selected-pair` as foundations only; this release therefore always reports `selected_path: unverified`. A remote `relay` or `tcp` candidate does **not** establish that TURN/TCP was selected, and cannot establish that a client firewall blocks UDP. This release does not correlate TURN allocations, public client IPs, ASN, or network groups. `top` shows the abbreviated remote candidate-type inventory as `R-CAND`, not a chosen route. Parsing is best-effort because candidate field formats can differ between Janus builds; unknowns are not guessed.

## Live mode (`top`) — version 0.1.3

The terminal live view shows an ephemeral `H1`, `H2`, ... label for each Janus handle, its VideoRoom role (publisher/subscriber, when reported), ICE and DTLS states, per-direction **audio/video traffic**, RTCP RTT (when positive and available), remote ICE candidate-type counts (R-CAND), and finding counts. Media rates use Janus `bytes_lastsec * 8 / 1000`, displayed as kbit/s (k) or Mbit/s (M). `--` means not available; zero means Janus reported zero. Totals sum only known audio/video flows from observed handles. They are **not** physical interface rates, unique conference bandwidth, or packet-loss percentages. Data channels are not added to media totals.

`top` additionally checks the same negotiated incoming/outgoing audio/video flow across refreshes. If positive `bytes_lastsec` was previously observed and then **three consecutive successful refreshes** report zero while ICE and DTLS remain ready, it displays `MEDIA_FLOW_STOPPED` with the relevant direction. This is a **heuristic**: a mute, pause, subscription change, or a quiet source can produce the same result. It is not proof of an outage. Unknown values are not treated as zero; the history resets on errors, truncated scans, disconnects, or missing handles. The history exists **only while `top` is running**; `scan` remains a one-shot snapshot with no temporal alert.

The `Scan: complete/partial` label describes coverage of the current API poll, **not** whether a Talk conference is healthy. Scans remain capped by `max_handles`; use an appropriate limit for larger deployments. This is a plain terminal live view, not a full-screen graphical TUI.

## Optional components

These adapters remain **best-effort and limited**:

- **Signaling:** Configure `[signaling] metrics_url` for an allowlisted metrics endpoint. This provides selected aggregate metrics, not participant identities.
- **coturn:** Configure `[coturn] cli_host = "127.0.0.1"` and `cli_port = 5766`, plus `TALKDIAG_COTURN_PASSWORD`. The current adapter only allows loopback management connections and retrieves limited `ps` information. Its management CLI is plaintext: never expose it publicly.
- **Recording:** Configure `[recording] systemd_unit` only when the recording backend is managed by local systemd. The current adapter does **not** inspect container-managed recording services.

Unconfigured components are labeled `not_configured`; reachability is not a health verdict.

## Privacy and safe diagnostics

By default, `talkdiag` redacts session/handle IDs, opaque IDs, selected ICE pairs, and raw protocol structures. `--show-sensitive` reveals identifying metadata, and `--raw` (which requires it) can contain **IP addresses, SDP, transport details, fingerprints, and potentially sensitive tokens**. Keep raw reports in protected local storage; sanitize them before posting to tickets, chat, or issue trackers.

Neither administrator credentials nor complete raw dumps should be committed to source control. Read-only API calls still add load: scans are limited by `max_handles` and the live refresh interval has a minimum of one second. No packet capture, media recording or passive monitoring daemon is included.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The test suite uses artificial API fixtures; it does not require a running Janus installation.

## Patch upgrades

A patch archive contains **only added or modified repository-relative paths** and may contain a `deletions.txt` file listing paths to remove. Apply it from the parent directory of `talkdiag-repo` using `unzip -o` (or inspect the archive first). Always review `deletions.txt` before removing anything. Back up local modifications. Configuration files containing secrets are **not** included in patch releases.

Example, from the directory containing `talkdiag-repo`:

```bash
unzip -o talkdiag-v0.1.3-patch.zip
cd talkdiag-repo
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The 0.1.3 patch is based on 0.1.2. Apply intermediate patches in order when upgrading from older versions.

## References

- [Janus Admin/Monitor API](https://janus.conf.meetecho.com/docs/admin.html)
- [Nextcloud Signaling metrics](https://nextcloud-spreed-signaling.readthedocs.io/en/latest/prometheus-metrics/)
- [coturn](https://github.com/coturn/coturn)

MIT License. Unofficial community utility; not affiliated with Nextcloud GmbH.
