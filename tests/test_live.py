import unittest
from talkdiag.live import LiveAnalyzer, rates, rate_label, render_top, rtt_ms


def handle(bytes_lastsec, key=(1, 2), ready=True, role='publisher'):
    return {
        '_tracking_key': key,
        'plugin_type': role,
        'ice': {'state': 'ready' if ready else 'disconnected'},
        'dtls': {'state': 'connected'},
        'flags': {'negotiated': True},
        'streams': [
            {'mindex': 1, 'type': 'video', 'direction': {'recv': True, 'send': False},
             'in': {'bytes_lastsec': bytes_lastsec}, 'out': {'bytes_lastsec': 0},
             'rtcp': {'rtt': 25}},
            {'mindex': 2, 'type': 'data', 'direction': {}, 'in': {'bytes_lastsec': None}},
        ], 'findings': [],
    }


def snap(row, errors=None, truncated=False):
    return {'session_count': 1, 'handles_scanned': 1, 'handles': [row], 'errors': errors or [], 'truncated': truncated}


class LiveTests(unittest.TestCase):
    def test_rates_and_display(self):
        h = handle(28819)
        self.assertAlmostEqual(rates(h, 'video')[0], 230.552)
        self.assertEqual(rates(h, 'audio'), (None, None))
        self.assertEqual(rtt_ms(h), 25)
        self.assertEqual(rate_label(230.552), '231k')
        output = render_top(snap(h))
        self.assertIn('Scan: complete', output)
        self.assertIn('231k/0k', output)
        self.assertIn('publisher', output)
        self.assertIn('25ms', output)
        self.assertNotIn('False', output)

    def test_temporal_stall_only_after_active_flow(self):
        engine = LiveAnalyzer(zero_samples=3)
        for _ in range(5):
            self.assertEqual(engine.update(snap(handle(0)))['handles'][0]['live_findings'], [])
        engine.update(snap(handle(1000)))
        for _ in range(2):
            self.assertEqual(engine.update(snap(handle(0)))['handles'][0]['live_findings'], [])
        result = engine.update(snap(handle(0)))
        self.assertEqual(result['handles'][0]['live_findings'][0]['code'], 'MEDIA_FLOW_STOPPED')
        self.assertIn('zero bytes_lastsec', result['handles'][0]['live_findings'][0]['evidence'])
        self.assertEqual(len(engine.update(snap(handle(0)))['handles'][0]['live_findings']), 1)
        self.assertEqual(engine.update(snap(handle(1000)))['handles'][0]['live_findings'], [])
        self.assertEqual(engine.update(snap(handle(0)))['handles'][0]['live_findings'], [])

    def test_state_resets_on_disconnect_or_incomplete_scan(self):
        engine = LiveAnalyzer()
        engine.update(snap(handle(120)))
        engine.update(snap(handle(0)))
        engine.update(snap(handle(0, ready=False)))
        self.assertFalse(engine.flows)
        self.assertEqual(engine.update(snap(handle(0)))['handles'][0]['live_findings'], [])
        engine.update(snap(handle(120)))
        engine.update(snap(handle(0)))
        engine.update(snap(handle(0), truncated=True))
        self.assertFalse(engine.flows)

    def test_missing_stats_not_diagnosed(self):
        engine = LiveAnalyzer()
        engine.update(snap(handle(100)))
        for _ in range(5):
            self.assertEqual(engine.update(snap(handle(None)))['handles'][0]['live_findings'], [])

    def test_separate_handles_not_mixed(self):
        engine = LiveAnalyzer()
        engine.update(snap(handle(100, key=(1, 2))))
        for _ in range(4):
            self.assertEqual(engine.update(snap(handle(0, key=(1, 3))))['handles'][0]['live_findings'], [])

    def test_partial_render(self):
        self.assertIn('Scan: partial', render_top(snap(handle(200), errors=[{'error': 'timeout'}])))

if __name__ == '__main__':
    unittest.main()
