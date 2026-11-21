"""Correlate frozen Vector logs with one collector snapshot; temporal context, not causality."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import networkx as nx
from graph_indexer.indexer import build_graph, digest, read, summarize


def timestamp(value):
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone is required')
    return result.astimezone(timezone.utc)


def correlate(snapshot, inventory, records, snapshot_path, lookback_seconds=60):
    if not math.isfinite(lookback_seconds) or lookback_seconds < 0:
        raise ValueError('Lookback must be finite and nonnegative')
    graph = build_graph(snapshot, inventory, snapshot_path)
    start, end = timestamp(snapshot['started_at']), timestamp(snapshot['completed_at'])
    if start > end:
        raise ValueError('Reversed snapshot window')
    lower = start - timedelta(seconds=lookback_seconds)
    sid = 'snapshot:' + hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    graph.add_node(sid, kind='snapshot', started_at=snapshot['started_at'], completed_at=snapshot['completed_at'],
                   status=snapshot['status'], evidence={'snapshot': snapshot_path})
    for router, item in snapshot['routers'].items():
        for kind, source in item['sources'].items():
            oid = f'{sid}:observation:{router}:{kind}'
            graph.add_node(oid, kind='observation', router=router, source=kind,
                status=source['status'], started_at=source.get('started_at'), completed_at=source.get('completed_at'),
                evidence=dict(snapshot=snapshot_path, pointer=f'/routers/{router}/sources/{kind}', raw_file=source.get('raw_file')))
            graph.add_edge(oid, sid, kind='part_of')
            graph.add_edge(oid, 'router:' + router, kind='observes_router')
    counts = Counter()
    excluded = []
    for record in records:
        event, evidence = record['event'], record['evidence']
        reason = None
        if not isinstance(event, dict) or event.get('schema_version') != 1:
            reason = 'invalid_schema'
        elif event.get('lab') != snapshot['lab']:
            reason = 'wrong_lab'
        elif 'router:' + str(event.get('router')) not in graph:
            reason = 'unknown_router'
        else:
            try:
                when = timestamp(event['event_timestamp'])
                timestamp(event['ingested_at'])
                if not isinstance(event['raw_message'], str):
                    raise ValueError('Missing raw message')
                if when < lower:
                    reason = 'outside_lookback'
                elif when > end:
                    reason = 'after_snapshot'
            except (TypeError, ValueError, KeyError):
                reason = 'invalid_or_missing_timestamp_or_message'
        if reason:
            counts[reason] += 1
            excluded.append(dict(reason=reason, evidence=evidence))
            continue
        identity = [event['lab'], event['router'], event['event_timestamp'], event['raw_message']]
        eid = 'log:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        if eid in graph:
            graph.nodes[eid]['evidence'].append(evidence)
            counts['duplicate'] += 1
            continue
        graph.add_node(eid, kind='log_event', event=event, evidence=[evidence])
        graph.add_edge(eid, 'router:' + event['router'], kind='emitted_by')
        graph.add_edge(eid, sid, kind='temporal_context', relation='before' if when < start else 'during',
            delta_to_snapshot_start_seconds=(when - start).total_seconds(), causal_claim=False)
        protocol = {'BGP': 'bgp', 'OSPF': 'ospf'}.get(event.get('daemon'))
        oid = f'{sid}:observation:{event["router"]}:{protocol}'
        if protocol and oid in graph:
            source = graph.nodes[oid]
            relation = 'unknown'
            if source['started_at'] and source['completed_at']:
                a, b = timestamp(source['started_at']), timestamp(source['completed_at'])
                relation = 'before' if when < a else ('after' if when > b else 'during')
            graph.add_edge(eid, oid, kind='protocol_context', relation=relation,
                observation_status=source['status'], causal_claim=False)
        counts['matched'] += 1
    report = dict(counts=dict(counts), excluded=excluded, lookback_seconds=lookback_seconds,
        window_start=lower.isoformat(), window_end=end.isoformat(),
        semantics='Inclusive event-time window; ingest time is not event time; context does not assert cause or peer/interface identity',
        topology=summarize(graph))
    graph.graph['correlation'] = {k: v for k, v in report.items() if k not in ('excluded', 'topology')}
    return graph, report


def export(snapshot_path, inventory_path, log_dir, output, lookback_seconds=60):
    records, invalid, manifest = [], [], []
    for path in sorted(log_dir.rglob('*.jsonl')):
        content = path.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        manifest.append(dict(path=str(path), sha256=sha))
        for line_number, line in enumerate(content.decode('utf-8').splitlines(), 1):
            evidence = dict(path=str(path), line=line_number, sha256=sha)
            try:
                records.append(dict(event=json.loads(line), evidence=evidence))
            except json.JSONDecodeError:
                invalid.append(dict(reason='invalid_json', evidence=evidence))
    if not manifest:
        raise ValueError('No frozen JSONL files found')
    graph, report = correlate(read(snapshot_path), read(inventory_path), records, str(snapshot_path), lookback_seconds)
    report['invalid_json'] = invalid
    report['inputs'] = manifest
    graph.graph.update(snapshot_sha256=digest(snapshot_path), inventory_sha256=digest(inventory_path),
                       networkx_version=nx.__version__, log_inputs=manifest)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('graph.json', nx.node_link_data(graph, edges='edges')), ('correlation.json', report)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return graph, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path)
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--logs', type=Path, required=True, help='Frozen JSONL directory')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--lookback', type=float, default=60)
    args = p.parse_args()
    _, report = export(args.snapshot, args.inventory, args.logs, args.output, args.lookback)
    print(json.dumps(report['counts']))


if __name__ == '__main__':
    main()
