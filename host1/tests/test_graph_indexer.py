"""Replay real evidence and test missing-source semantics; no Docker commands."""
import copy
import json
from pathlib import Path
import unittest

import networkx as nx
from graph_indexer.indexer import build_graph, export, read, summarize, ROOT

BASE = ROOT / 'data/host1/telemetry/20261119T050248Z-fbeea22b'
FAULT = ROOT / 'data/host1/telemetry-faults/20261119T052911130023Z'


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = read(BASE / '0001/snapshot.json')
        self.plan = read(BASE / 'inventory.json')

    def test_partial_is_unknown(self):
        for router in ('r1', 'r2'):
            for source in ('interfaces', 'ospf', 'bgp', 'routes'):
                self.snapshot['routers'][router]['sources'][source].update(status='error', data=None)
        graph = build_graph(self.snapshot, self.plan)
        self.assertEqual(summarize(graph)['physical_links']['L12'], 'unknown')
        self.assertEqual(graph['router:r1']['router:r2']['ospf:L12']['state'], 'unknown')
        self.assertEqual(graph['router:r1']['router:r2']['bgp:ibgp']['state'], 'unknown')
        self.assertNotIn('r1', summarize(graph)['installed_egress'])

    def test_missing_interface_not_inferred_up(self):
        self.snapshot['routers']['r1']['sources']['interfaces']['data'] = []
        self.assertEqual(summarize(build_graph(self.snapshot, self.plan))['physical_links']['L12'], 'unknown')

    def test_mtu_mismatch_separate_from_link_state(self):
        for i in self.snapshot['routers']['r1']['sources']['interfaces']['data']:
            if i['name'] == 'eth1':
                i['mtu'] = 1400
        graph = build_graph(self.snapshot, self.plan)
        edge = graph['interface:r1:eth1']['interface:r2:eth1']['L12']
        self.assertEqual(edge['state'], 'up')
        self.assertFalse(edge['mtu_matches_expected'])

    def test_schema_and_lab_rejected(self):
        for key, value in [('schema_version', 2), ('lab', 'other')]:
            altered = copy.deepcopy(self.snapshot)
            altered[key] = value
            with self.assertRaises(ValueError):
                build_graph(altered, self.plan)

    def test_roundtrip_and_parallel_relations(self):
        graph = build_graph(self.snapshot, self.plan)
        restored = nx.node_link_graph(json.loads(json.dumps(nx.node_link_data(graph, edges='edges'))), edges='edges')
        self.assertEqual(summarize(graph), summarize(restored))
        self.assertEqual(set(graph['router:r1']['router:r2']), {'ospf:L12', 'bgp:ibgp'})


def replay(output):
    rows = []
    for root in (BASE, FAULT):
        for path in sorted(root.rglob('snapshot.json')):
            # Only collector snapshots, not the independent runtime verifier.
            if read(path).get('schema_version') != 1 or 'source_counts' not in read(path):
                continue
            relative = path.relative_to(root)
            graph = export(path, root / 'inventory.json', output / root.parent.name / relative.parent)
            summary = summarize(graph)
            loaded = nx.node_link_graph(read(output / root.parent.name / relative.parent / 'graph.json'), edges='edges')
            assert summarize(loaded) == summary, 'JSON round-trip changed graph'
            label = str(relative).replace('\\', '/')
            expected = None
            if root == BASE or '/before/' in '/' + label or label.endswith('restored/0003/snapshot.json'):
                expected = (8, 5, 9, 'eth1', 'eth2')
            elif '/down/' in label:
                expected = (7, 4, 9, 'eth2', 'eth2') if label.startswith('L12/') else (7, 5, 8, 'eth1', 'eth1')
            actual = (sum(v == 'up' for v in summary['physical_links'].values()),
                      summary['healthy_unique_sessions']['ospf'], summary['healthy_unique_sessions']['bgp'],
                      summary['installed_egress']['r1']['10.100.6.1/32'][0]['interfaceName'],
                      summary['installed_egress']['r1']['10.100.5.1/32'][0]['interfaceName'])
            if expected:
                assert actual == expected, (label, actual, expected)
            if '/down/' in label and label.startswith('L35/'):
                for a, b in [('r3', 'r5'), ('r5', 'r3')]:
                    observed = read(path)['routers'][a]['sources']['bgp']['data']['peers']
                    peer = next(p for p in observed if p['address'].startswith('10.0.35.'))
                    assert graph['router:' + a]['router:' + b]['bgp:L35']['state'] == peer['state']
                    assert peer['state'] in ('Idle', 'Active')
            rows.append(dict(snapshot=str(path.relative_to(ROOT)), checked_state=expected is not None,
                             actual=actual, expected=expected, nodes=len(graph), edges=graph.number_of_edges()))
    assert len(rows) == 15, len(rows)
    report = dict(passed=True, snapshot_count=len(rows), state_checked=sum(r['checked_state'] for r in rows),
                  columns=['physical_up', 'ospf_full_unique', 'bgp_established_unique', 'r1_to_r6_egress', 'r1_to_r5_egress'],
                  snapshots=rows)
    (output / 'replay-validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        replay(Path(sys.argv[2]))
    else:
        unittest.main()
