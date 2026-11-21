"""Validate real L12/L35 log events against frozen telemetry and correlated graphs."""
import json
from pathlib import Path
import sys

import networkx as nx
from graph_indexer.correlate import export, timestamp
from graph_indexer.indexer import read


def main(run):
    actions = read(run / 'events.json')
    rows, errors = [], []
    for case, endpoints, protocol, prefix, normal, fault in [
        ('L12', [('r1', '10.255.0.2'), ('r2', '10.255.0.1')], 'ospf', '10.100.6.1/32', 'eth1', 'eth2'),
        ('L35', [('r3', '10.0.35.2'), ('r5', '10.0.35.1')], 'bgp', '10.100.5.1/32', 'eth2', 'eth1')]:
        down_at = timestamp(next(e['time_utc'] for e in actions if e['action'] == 'down_requested' and e['link'] == case))
        up_at = timestamp(next(e['time_utc'] for e in actions if e['action'] == 'up_applied' and e['link'] == case))
        result = read(run / case / 'result.json')
        paths = {'before': run / case / 'before/snapshot.json',
                 'down': run / result['down']['snapshot'], 'restored': run / result['restored']['snapshot']}
        for phase, path in paths.items():
            output = run / 'graphs' / case / phase
            graph, report = export(path, run / 'inventory.json', run / 'logs', output)
            loaded = nx.node_link_graph(read(output / 'graph.json'), edges='edges')
            if not nx.utils.graphs_equal(graph, loaded):
                errors.append(f'{case}/{phase}: round-trip mismatch')
            topo = report['topology']
            want_sessions = {'ospf': 4 if case == 'L12' and phase == 'down' else 5,
                             'bgp': 8 if case == 'L35' and phase == 'down' else 9}
            want_egress = fault if phase == 'down' else normal
            if topo['healthy_unique_sessions'] != want_sessions:
                errors.append(f'{case}/{phase}: protocol counts')
            if topo['physical_links'][case] != ('down' if phase == 'down' else 'up'):
                errors.append(f'{case}/{phase}: link state')
            if {h['interfaceName'] for h in topo['installed_egress']['r1'][prefix]} != {want_egress}:
                errors.append(f'{case}/{phase}: egress')
            logs = [(eid, node) for eid, node in graph.nodes(data=True) if node['kind'] == 'log_event']
            evidence_rows = []
            for router, peer in endpoints:
                for direction in (['down', 'up'] if phase == 'restored' else ['down']):
                    matches = []
                    for eid, node in logs:
                        event = node['event']
                        msg = event['message']
                        if event['router'] != router or event['daemon'] != protocol.upper() or peer not in msg:
                            continue
                        when = timestamp(event['event_timestamp'])
                        if when < down_at:
                            continue
                        if protocol == 'ospf':
                            match = 'AdjChg:' in msg and ('Full -> Deleted' in msg if direction == 'down' else '-> Full' in msg)
                        else:
                            match = '%ADJCHANGE:' in msg and (' Down ' in msg if direction == 'down' else msg.endswith(' Up'))
                        if not match:
                            continue
                        # up_applied is recorded after command completion; very fast daemon events may precede it slightly.
                        if direction == 'down' and when >= up_at:
                            continue
                        edges = [(target, edge) for _, target, edge in graph.out_edges(eid, data=True)
                                 if edge['kind'] == 'protocol_context']
                        if len(edges) != 1 or graph.nodes[edges[0][0]]['router'] != router or graph.nodes[edges[0][0]]['source'] != protocol:
                            errors.append(f'{case}/{phase}: wrong protocol context {router}')
                        if not graph.has_edge(eid, 'router:' + router):
                            errors.append(f'{case}/{phase}: wrong router edge')
                        if event['raw_message'] not in (run / 'frr-raw' / router / 'events.log').read_text():
                            errors.append(f'{case}/{phase}: raw FRR evidence missing')
                        matches.append(dict(event_id=eid, event=event, evidence=node['evidence'],
                                            protocol_context=[dict(target=t, **e) for t, e in edges]))
                    expected_count = 0 if phase == 'before' else 1
                    if len(matches) != expected_count:
                        errors.append(f'{case}/{phase}/{router}/{direction}: expected {expected_count} real transitions, got {len(matches)}')
                    evidence_rows.append(dict(router=router, direction=direction, matches=matches))
            # Recovery logs must not leak into a pre-recovery snapshot.
            if phase == 'down':
                for _, node in logs:
                    if timestamp(node['event']['event_timestamp']) > timestamp(read(path)['completed_at']):
                        errors.append(f'{case}/down: future event leaked')
            rows.append(dict(case=case, phase=phase, source_snapshot=str(path.relative_to(run)),
                topology=topo, counts=report['counts'], transitions=evidence_rows))
    baseline = read(run / 'baseline-after-L35/verification-summary.json')
    if not baseline['passed'] or not read(run / 'summary.json')['passed']:
        errors.append('Runtime baseline/config comparison failed')
    output = dict(passed=not errors, errors=errors, graphs_checked=len(rows), scenarios=rows,
                  baseline=baseline, scope='One live trial per link; temporal correlation only, not automated RCA')
    (run / 'correlation-validation.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(dict(passed=not errors, errors=errors, graphs_checked=len(rows)), indent=2))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
