"""Replay six stored baseline/fault/restored graphs; no Docker or network mutation."""
import json
from pathlib import Path
import sys
from knowledge.evidence import ROOT, retrieve_bundle, read

RUN = ROOT / 'data/host1/integration-faults/20261119T100613Z'


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for link, protocol, endpoints in [('L12', 'ospf', {'r1', 'r2'}), ('L35', 'bgp', {'r3', 'r5'})]:
        for phase in ('before', 'down', 'restored'):
            bundle = retrieve_bundle(RUN / 'graphs' / link / phase / 'graph.json', RUN / 'inventory.json', link)
            ctx = bundle['evidence']
            expected_state = 'down' if phase == 'down' else 'up'
            healthy = all(s['state'] == 'Established' if protocol == 'bgp' else s['state'].startswith('Full')
                          for s in ctx['sessions'])
            logs = ctx['logs']
            down_logs = [l for l in logs if ('AdjChg:' in l['event']['message'] and 'Full -> Deleted' in l['event']['message'] if protocol == 'ospf'
                         else ' Down ' in l['event']['message'])]
            up_logs = [l for l in logs if ('AdjChg:' in l['event']['message'] and '-> Full' in l['event']['message'] if protocol == 'ospf'
                       else l['event']['message'].endswith(' Up'))]
            # Target fault transitions: baseline must not contain future down/up records for these peers.
            transition_ok = (not down_logs and not up_logs if phase == 'before' else
                             len(down_logs) == 2 and (not up_logs if phase == 'down' else len(up_logs) == 2))
            checks = dict(physical=all(e['state'] == expected_state for e in ctx['physical']),
                sessions=healthy == (phase != 'down'), transitions=transition_ok,
                scoped_logs=all(l['event']['router'] in endpoints and l['event']['daemon'] == protocol.upper() for l in logs),
                citations=all(len(d['retrieval']['hits']) == 5 for d in bundle['documentation']),
                no_diagnosis_or_patch=bundle['diagnosis'] is None and bundle['executable_patch'] is None,
                log_retrieval=any(any('graph_node' in r for r in d['trigger_evidence']) for d in bundle['documentation']) if logs else True)
            # Semantic review aids: report matching excerpts, not an automatic relevance score.
            needles = ['adjacency', 'neighbor'] if protocol == 'ospf' else ['fast-external-failover', 'session-state', 'neighbor']
            terms = {term: sum(term.lower() in hit['text'].lower() for d in bundle['documentation']
                              for hit in d['retrieval']['hits']) for term in needles}
            (output / f'{link}-{phase}.json').write_text(json.dumps(bundle, indent=2) + '\n')
            row = dict(link=link, phase=phase, passed=all(checks.values()), checks=checks,
                state=expected_state, protocol_states=[s['state'] for s in ctx['sessions']],
                logs=len(logs), down_events=len(down_logs), up_events=len(up_logs),
                omitted=ctx['omitted_other_router_or_protocol_events'], retrievals=len(bundle['documentation']),
                documentation_term_hits=terms)
            rows.append(row)
            print(json.dumps(row), flush=True)
    summary = dict(passed=all(row['passed'] for row in rows), scenarios=rows,
                   scope='Stored six-graph replay; provenance/state/temporal checks, not independent RCA or retrieval relevance benchmark')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
