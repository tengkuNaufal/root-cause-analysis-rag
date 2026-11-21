import copy
import unittest
from graph_indexer.correlate import correlate
from graph_indexer.indexer import ROOT, read


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'data/host1/telemetry/20261119T050248Z-fbeea22b'
        self.s = read(base / '0001/snapshot.json')
        self.p = read(base / 'inventory.json')
        self.s.update(started_at='2026-11-19T10:00:00Z', completed_at='2026-11-19T10:00:01Z')
        self.e = dict(schema_version=1, lab='rca', router='r1', daemon='BGP',
            raw_message='marker', message='marker', event_timestamp='2026-11-19T09:59:59Z',
            ingested_at='2026-11-19T10:05:00.123456789Z')

    def build(self, events):
        return correlate(self.s, self.p, [dict(event=e, evidence={'line': n}) for n, e in enumerate(events, 1)], 'test')

    def test_event_time_not_ingest_time_and_protocol_mapping(self):
        g, r = self.build([self.e])
        self.assertEqual(r['counts']['matched'], 1)
        log = next(n for n, d in g.nodes(data=True) if d['kind'] == 'log_event')
        self.assertTrue(g.has_edge(log, 'router:r1'))
        targets = [g.nodes[b] for _, b, d in g.out_edges(log, data=True) if d['kind'] == 'protocol_context']
        self.assertEqual([(d['router'], d['source']) for d in targets], [('r1', 'bgp')])

    def test_future_old_unknown_and_missing_time_excluded(self):
        events = []
        for key, value in [('event_timestamp', '2026-11-19T10:00:02Z'),
                           ('event_timestamp', '2026-11-19T09:58:59Z'), ('router', 'r99'),
                           ('event_timestamp', None), ('lab', 'other')]:
            events.append(dict(self.e, **{key: value}))
        _, r = self.build(events)
        self.assertEqual(sum(r['counts'].values()), 5)
        self.assertEqual(r['counts'].get('matched', 0), 0)

    def test_deduplicate_preserves_evidence(self):
        g, r = self.build([self.e, self.e.copy()])
        self.assertEqual(r['counts'], {'matched': 1, 'duplicate': 1})
        node = next(d for _, d in g.nodes(data=True) if d['kind'] == 'log_event')
        self.assertEqual(len(node['evidence']), 2)

    def test_partial_observation_never_implies_healthy(self):
        self.s['routers']['r1']['sources']['bgp'].update(status='error', data=None)
        g, _ = self.build([self.e])
        context = next(d for _, _, d in g.edges(data=True) if d['kind'] == 'protocol_context')
        self.assertEqual(context['observation_status'], 'error')
        self.assertFalse(context['causal_claim'])
        self.assertEqual(g['router:r1']['router:r2']['bgp:ibgp']['state'], 'unknown')

    def test_inclusive_boundaries_and_no_timezone(self):
        events = [dict(self.e, event_timestamp=t) for t in
                  ['2026-11-19T09:59:00Z', '2026-11-19T10:00:01Z', '2026-11-19T10:00:00']]
        _, r = self.build(events)
        self.assertEqual(r['counts']['matched'], 2)
        self.assertEqual(r['counts']['invalid_or_missing_timestamp_or_message'], 1)


if __name__ == '__main__':
    unittest.main()
