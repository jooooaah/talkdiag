import json
import unittest
from talkdiag.network import summarize_candidates, ice_network
from talkdiag.cli import handle_summary, one_shot, parser
from talkdiag.config import Config
from unittest.mock import patch


class IceNetworkTests(unittest.TestCase):
    def test_sdp_and_structured_candidates(self):
        candidates = [
            'candidate:123 1 UDP 2122260223 192.0.2.42 53492 typ host generation 0',
            'candidate:456 1 tcp 16777215 198.51.100.12 443 typ relay tcptype passive',
            {'type': 'srflx', 'protocol': 'udp', 'address': '203.0.113.13'},
        ]
        parsed = summarize_candidates(candidates)
        self.assertEqual(parsed['types'], {'host': 1, 'relay': 1, 'srflx': 1})
        self.assertEqual(parsed['protocols'], {'udp': 2, 'tcp': 1})
        self.assertEqual(parsed['unclassified'], 0)
        self.assertNotIn('192.0.2.42', json.dumps(parsed))

    def test_unavailable_vs_empty_vs_unknown(self):
        self.assertFalse(summarize_candidates(None)['available'])
        self.assertEqual(summarize_candidates([])['count'], 0)
        value = summarize_candidates(['unrecognized private string 192.0.2.7'])
        self.assertEqual(value['unclassified'], 1)
        self.assertEqual(value['types'], {})
        self.assertNotIn('192.0.2.7', json.dumps(value))

    def test_foundations_do_not_prove_selected_transport(self):
        parsed = ice_network({'selected-pair': '1:2', 'remote-candidates': [
            'candidate:9 1 TCP 42 192.0.2.1 443 typ relay']})
        self.assertTrue(parsed['selected_pair_observed'])
        self.assertEqual(parsed['selected_path'], 'unverified')
        self.assertIn('relay', parsed['remote_candidates']['types'])

    def test_no_raw_candidate_leak_in_default_or_sensitive_summary(self):
        info = {'plugin': 'janus.plugin.videoroom', 'webrtc': {'ice': {
            'state': 'ready', 'selected-pair': 'secret foundations',
            'remote-candidates': ['candidate:9 1 TCP 42 192.0.2.9 443 typ relay'],
            'local-candidates': ['candidate:7 1 UDP 42 10.0.0.9 555 typ host'],
        }}}
        for enabled in (False, True):
            summary = handle_summary(123, 456, info, enabled)
            serialized = json.dumps(summary)
            self.assertNotIn('192.0.2.9', serialized)
            self.assertNotIn('10.0.0.9', serialized)
            self.assertEqual(summary['network']['selected_path'], 'unverified')
            self.assertEqual(summary['network']['remote_candidates']['types']['relay'], 1)
        self.assertEqual(handle_summary(123, 456, info)['ice']['selected_pair'], '[redacted]')

    def test_paths_cli_projection(self):
        class MockJanus:
            def __init__(self, cfg): pass
            def sessions(self): return [123]
            def handles(self, sid): return [456]
            def handle_info(self, sid, hid):
                return {'webrtc': {'ice': {'remote-candidates': [{'type': 'relay', 'protocol': 'tcp'}]}}}
        args = parser().parse_args(['paths'])
        with patch('talkdiag.cli.Janus', MockJanus):
            payload = one_shot(args, Config())
        self.assertEqual(payload['paths'][0]['network']['remote_candidates']['types'], {'relay': 1})
        self.assertNotIn('_tracking_key', json.dumps(payload))


if __name__ == '__main__':
    unittest.main()
