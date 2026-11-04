import io
import unittest
from unittest.mock import patch
from talkdiag.cli import demo_data, browser_help, handle_summary, scan_janus, main
from talkdiag.config import Config
from talkdiag.janus import Janus, JanusError
from talkdiag.components import signaling_metrics

class FakeJanus:
    def sessions(self): return [11]
    def handles(self, session): return [21, 22]
    def handle_info(self, session, handle):
        return {"plugin": "janus.plugin.videoroom", "streams": [{"ice": "disconnected"}], "queued-packets": 101}

class ToolTests(unittest.TestCase):
    def test_demo_offline(self):
        self.assertTrue(demo_data()["sample"])
        self.assertEqual(main(["--json", "demo"]), 0)

    def test_browser_help(self):
        report = browser_help("firefox", "ice")
        self.assertEqual(report["page"], "about:webrtc")

    def test_scan_and_limit(self):
        result = scan_janus(FakeJanus(), 1, False)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["handles_scanned"], 1)
        self.assertEqual(result["handles"][0]["handle"], "[redacted]")
        self.assertEqual(result["handles"][0]["findings"][0]["code"], "QUEUE_HIGH")

    def test_handle_sensitive(self):
        obj = handle_summary(11, 22, {"opaque_id": "alice", "streams": []}, True)
        self.assertEqual(obj["opaque_id"], "alice")
        self.assertEqual(handle_summary(11, 22, {"opaque_id": "alice"})["opaque_id"], "[redacted]")

    def test_reject_mutating_janus(self):
        with self.assertRaises(JanusError):
            Janus(Config()).call("destroy_session")

    def test_unconfigured_metrics(self):
        self.assertEqual(signaling_metrics(Config())["status"], "not_configured")

    def test_requires_explicit_raw(self):
        with patch("talkdiag.cli.Janus") as cls:
            cls.return_value.handle_info.return_value = {"sdps": {"remote": "private"}}
            self.assertEqual(main(["inspect", "--session", "1", "--handle", "2", "--raw"]), 2)

if __name__ == "__main__":
    unittest.main()

class JanusSchemaTests(unittest.TestCase):
    def setUp(self):
        self.info = {
            "plugin": "janus.plugin.videoroom",
            "plugin_specific": {"type": "publisher", "streams": [
                {"type": "audio", "mindex": 0, "mid": "0", "codec": "opus", "subscribers": 2}
            ]},
            "flags": {"ready": True, "negotiated": True},
            "queued-packets": 0,
            "webrtc": {
                "ice": {"state": "connected", "selected-pair": "10.0.0.1:1234 <-> 192.0.2.1:4321", "ready": 1},
                "dtls": {"dtls-state": "connected", "ready": True},
                "media": {
                    "0": {"type": "audio", "mindex": 0, "mid": "0",
                          "direction": {"send": True, "recv": True},
                          "codecs": {"codec": "opus"},
                          "stats": {"in": {"packets": 100, "bytes": 40000, "bytes_lastsec": 2000},
                                    "out": {"packets": 80, "bytes": 30000, "bytes_lastsec": 1000}},
                          "rtcp": {"main": {"rtt": 25, "lost": 3, "lost-by-remote": 2,
                                            "jitter-local": 5, "jitter-remote": 4}}},
                    "1": {"type": "video", "mindex": 1,
                          "stats": {"in": {"packets": 20}, "out": {"packets": 10}}}
                },
            },
        }

    def test_nested_janus_media(self):
        from talkdiag.diagnosis import flatten_stream_state
        parsed = flatten_stream_state(self.info)
        self.assertEqual(parsed["stream_count"], 2)
        self.assertEqual(parsed["plugin_stream_count"], 1)
        self.assertEqual(parsed["ice"]["state"], "connected")
        self.assertEqual(parsed["dtls"]["state"], "connected")
        self.assertEqual(parsed["streams"][0]["in"]["bytes_lastsec"], 2000)
        self.assertEqual(parsed["streams"][0]["rtcp"]["lost_by_remote_total"], 2)

    def test_sensitive_candidate_pair_redacted(self):
        result = handle_summary(11, 22, self.info)
        self.assertEqual(result["ice"]["selected_pair"], "[redacted]")
        result_sensitive = handle_summary(11, 22, self.info, True)
        self.assertIn("10.0.0.1", result_sensitive["ice"]["selected_pair"])

    def test_janus_failure_state(self):
        from talkdiag.diagnosis import findings
        self.info["webrtc"]["ice"]["state"] = "disconnected"
        self.assertIn("ICE_UNSTABLE", [item["code"] for item in findings(self.info)])

    def test_no_loss_percentage_claim(self):
        import json
        result = handle_summary(11, 22, self.info)
        self.assertNotIn("loss_pct", json.dumps(result))
