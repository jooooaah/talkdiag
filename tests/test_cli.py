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
