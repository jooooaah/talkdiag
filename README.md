# talkdiag 0.1.0 — Nextcloud Talk Server Diagnostics

**Experimentelles, lesendes CLI-Diagnosewerkzeug** für Nextcloud Talk / Janus / coturn. Kein Ersatz für Grafana. Python 3.11+, **keine Runtime-Abhängigkeiten**.

> **Wichtig:** Diese erste Version zeigt **Janus-Sessions und -Handles**, noch **keine eindeutig identifizierten Talk-Teilnehmer oder Räume**. Sie beweist keine Client-Firewallprobleme. Ein Janus-Handle ist nicht gleich einem Nutzer. Teste zuerst an einer eigenen Installation mit einer kleinen laufenden Testkonferenz.

## Schnellstart auf einem Talk-/HPB-Server (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv unzip
unzip talkdiag-v0.1.0.zip
cd talkdiag-repo
python3 -m venv .venv
cp config.example.toml config.toml
chmod 600 config.toml
./bin/talkdiag demo
./bin/talkdiag --help
```

**Kein `pip install` nötig!** Der mitgelieferte Starter `./bin/talkdiag` nutzt direkt das venv und den Quellcode im Repository. Es gibt keine Runtime-Pakete von PyPI. Alternativ kann man mit aktiviertem venv `PYTHONPATH=src python -m talkdiag ...` starten. Wer einen global verfügbaren Befehl möchte, kann optional mit `python -m pip install -e .` installieren (benötigt `setuptools` und möglicherweise einen Paketindex). Die Beispiele unten verwenden dann `talkdiag ...`; ohne Installation ist stets `./bin/talkdiag ...` gleichwertig.

### Janus Admin API konfigurieren

Das Tool erwartet eine **Janus Admin/Monitor HTTP API** (nicht die normale öffentliche Janus API). In vielen Installationen ist diese **standardmäßig abgeschaltet**. Sie wird im Janus-HTTP-Transport (z. B. `janus.transport.http.jcfg`) über den `[admin]`-Abschnitt aktiviert; der genaue Dateipfad hängt von Paket, Container und Deployment ab. Typisch ist HTTP auf Loopback-Port **7088**, aber die tatsächliche Konfiguration ist maßgeblich. Die Admin API sollte **nur lokal oder über einen SSH-Tunnel** zugänglich sein.

Beispiel für den Janus-HTTP-Transport (mit vorhandener Konfiguration abgleichen, **nicht blind überschreiben**):

```ini
admin: {
    admin_http = true
    admin_port = 7088
    admin_base_path = "/admin"
    admin_acl = "127.0.0.1"
}
```

Für die verwendete Janus-Version unbedingt die zugehörigen Konfigurationsdateien prüfen. Ein erforderliches Admin-Secret kann in `janus.jcfg` unter `admin_secret` konfiguriert sein. **Nicht** in eine ZIP, ein Ticket oder eine Shell-History übernehmen. Stattdessen interaktiv setzen:

```bash
read -rs -p 'Janus Admin Secret: ' TALKDIAG_JANUS_SECRET; echo
export TALKDIAG_JANUS_SECRET
```

Dann `config.toml` editieren (`[janus] admin_url = "http://127.0.0.1:7088/admin"`). Falls Janus remote läuft: SSH-Forwarding zum **loopbackgebundenen** Admin-Port verwenden, nicht den Port ins Internet öffnen.

### Testen

```bash
# Funktioniert ohne Serververbindung:
talkdiag demo
talkdiag client-help --browser firefox --issue ice

# Benötigt Janus Admin API:
talkdiag status
talkdiag sessions --help  # --json steht als globale Option davor:
talkdiag --json sessions
talkdiag --show-sensitive sessions

talkdiag --show-sensitive inspect --session 1234 --handle 5678
# Für vertrauliche Rohdaten explizit freigeben:
talkdiag --show-sensitive inspect --session 1234 --handle 5678 --raw

talkdiag scan
talkdiag --json scan > diag.json
talkdiag top --interval 3
```

Die Optionen `--json`, `--config`, `--show-sensitive` stehen **vor** dem Unterbefehl. `top` benötigt ein interaktives Terminal. Ohne Paketinstallation ersetzen durch `PYTHONPATH=src python3 -m talkdiag ...`.

### Optional: weitere Komponenten

`config.toml` kann zusätzlich aktiviert werden für:

- **Signaling:** `[signaling] metrics_url = "http://127.0.0.1:.../metrics"` (in signaling-Konfiguration muss die Abfrage-IP unter `[stats] allowed_ips` erlaubt sein). Zeigt ausgewählte Summenmetriken, keine einzelnen Teilnehmer.
- **coturn:** `[coturn] cli_host = "127.0.0.1"`, `cli_port = 5766`. Die Management-CLI kann im coturn-Konfigurationsfile ausgeschaltet sein. Zugangsdaten über `TALKDIAG_COTURN_PASSWORD`; die aktuelle Implementierung holt die **rohe `ps`-Ausgabe** als Best-Effort, zeigt standardmäßig keine sensiblen Angaben. TCP-Verbindung nur lokal; remote via SSH-Tunnel. Die CLI spricht **Klartext**, niemals öffentlich exponieren.
- **Recording:** `[recording] systemd_unit = "DEIN-RECORDING-SERVICE.service"`. Nur `systemctl is-active`, **keine** tiefgehende Recording-Diagnose; bei Docker nicht passend.

`talkdiag status` unterscheidet `reachable`, `inactive`, `error` und `not_configured`. Ein erreichbarer Dienst ist **nicht automatisch gesund**.

## Funktionsumfang 0.1.0

| Funktion | Stand |
|---|---|
| Janus Admin API Ping, Sessions, Handles, `handle_info` | Implementiert, read-only |
| Diagnosen `ICE_UNSTABLE` und `QUEUE_HIGH` | Implementiert, bewusst konservativ; Janus-Versionen können andere Felder nutzen |
| Text-Liveübersicht `top` | Implementiert, keine vollständige TUI |
| JSON-Ausgabe für Tickets/Logs | Implementiert |
| Client-Hinweise `client-help` | Firefox, Chrome, Edge; manueller Abgleich |
| coturn Management-CLI `ps` | Optional, Rohdaten/Best-Effort |
| Signaling Prometheus-Summenmetriken | Optional |
| Recording systemd-Status | Optional |
| Talk-Raum-/Teilnehmer-Identifikation | **Nicht implementiert** |
| IP-/ASN-Gruppierung, TURN-Clienttransport-Korrelation | **Nicht implementiert** |
| Browserreport-Import, Datensammlung im Hintergrund | **Nicht implementiert** |
| Firewall-Fernprüfung, verlässliche Paketverlustdiagnose | **Nicht implementiert** |

### Datenschutz / Betriebsrisiken

`--show-sensitive` kann IDs und `opaque_id` offenlegen. `--raw` kann **SDP, Client-IPs und andere sensible Metadaten** enthalten. Diese Dateien vor Versand redigieren. `coturn ps` enthält ggf. IPs und Nutzerinformationen und wird nur bei `--show-sensitive` ausgegeben. Keine Schreiboperationen an Janus, kein Mitschnitt von Medien, keine Root-Rechte erforderlich. Häufiges Pollen zahlreicher Handles erzeugt Admin-API-Last: `scan` ist auf 150 Handles limitiert (anpassbar über Config); `top` nicht schneller als alle 1 s.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Die Tests laufen ohne Janus/coturn. Für reale Integrationstests bitte `--show-sensitive inspect ... --raw` nur lokal nutzen und niemals unredigiert veröffentlichen.

## Änderungspakete für Folgereleases

Künftige Patch-ZIPs sollen **nur neue/geänderte Repository-Dateien** enthalten. Löschungen stehen zeilenweise als repo-relative Pfade in `deletions.txt`. Ein Patch-ZIP wird im Repository-Wurzelverzeichnis entpackt; `deletions.txt` vor dem Löschen prüfen. Baseline dieser Version: `0.1.0`.

## Dokumentation

- Janus Admin/Monitor API: https://janus.conf.meetecho.com/docs/admin.html
- Signaling Metrics: https://nextcloud-spreed-signaling.readthedocs.io/en/latest/prometheus-metrics/
- coturn: https://github.com/coturn/coturn/blob/master/README.turnserver

MIT License. Keine Verbindung zu einem offiziellen Nextcloud-Projekt.
