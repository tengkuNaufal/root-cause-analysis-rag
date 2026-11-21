"""Build and validate correlated graphs from capture_live evidence (offline, no faults)."""
import json
from pathlib import Path
import sys

import networkx as nx
from graph_indexer.correlate import export
from graph_indexer.indexer import read


def main(directory):
    expected = read(directory / 'expected.json')
    results = {}
    for phase in ('before', 'after'):
        output = directory / f'graph-{phase}'
        graph, report = export(directory / phase / 'snapshot.json', directory / 'inventory.json',
                               directory / 'logs', output)
        restored = nx.node_link_graph(read(output / 'graph.json'), edges='edges')
        assert nx.utils.graphs_equal(graph, restored), 'Graph JSON round-trip mismatch'
        logs = [(n, d) for n, d in graph.nodes(data=True) if d['kind'] == 'log_event']
        queries = {}
        for wanted in expected:
            matches = [(n, d) for n, d in logs if wanted['marker'] in d['event']['raw_message']]
            assert len(matches) == (1 if phase == 'after' else 0), (phase, wanted, len(matches))
            for eid, node in matches:
                event = node['event']
                assert event['router'] == wanted['router'] and event['daemon'] == wanted['daemon']
                assert graph.has_edge(eid, 'router:' + wanted['router'])
                contexts = [(target, edge) for _, target, edge in graph.out_edges(eid, data=True)
                            if edge['kind'] == 'protocol_context']
                assert len(contexts) == 1
                target, edge = contexts[0]
                observation = graph.nodes[target]
                assert observation['router'] == wanted['router']
                assert observation['source'] == wanted['daemon'].lower()
                assert observation['status'] == 'ok' and edge['relation'] == 'before'
                assert edge['causal_claim'] is False
                queries.setdefault(wanted['router'], []).append(dict(event_id=eid, event=event,
                    log_evidence=node['evidence'], snapshot_observation=observation, relation=edge))
        assert report['topology']['healthy_unique_sessions'] == {'ospf': 5, 'bgp': 9}
        assert all(s == 'up' for s in report['topology']['physical_links'].values())
        assert not report['invalid_json']
        results[phase] = dict(counts=report['counts'], graph_nodes=len(graph), graph_edges=graph.number_of_edges(),
                              tested_marker_count=10 if phase == 'after' else 0, queries=queries)
    summary = dict(passed=True, expected_markers=len(expected), phases=results,
                   scope='Host 1 live markers and snapshots; no network fault, no causal diagnosis')
    (directory / 'integration-validation.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'phases'}))
    print(json.dumps({p: {k: v for k, v in r.items() if k != 'queries'} for p, r in results.items()}))


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
