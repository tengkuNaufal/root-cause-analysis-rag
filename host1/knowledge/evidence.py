"""Join frozen NetworkX node-link exports to verified telemetry/logs and Chroma hits."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_path(value):
    value = str(value).replace('\\', '/')
    # Public fixtures use repository-relative paths. Rebase private legacy archives
    # by project directory name without embedding anyone's workstation location.
    prefix = ROOT.as_posix()
    if value == prefix or value.startswith(prefix + '/'):
        value = value[len(prefix):].lstrip('/')
    elif Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        for name in ('Tubes', 'root-cause-analysis-rag'):
            marker = '/' + name
            position = value.rfind(marker)
            suffix = value[position + len(marker):] if position >= 0 else None
            if suffix is not None and (not suffix or suffix.startswith('/')):
                value = suffix.lstrip('/')
                break
        else:
            raise ValueError('Evidence path outside project')
    mappings = (
        ('knowledge/models', 'private/knowledge/models'),
        ('knowledge/chroma', 'private/knowledge/chroma'),
        ('topology/frr/clab-rca', 'private/lab-runtime/clab-rca'),
        ('results', 'data/host1'), ('topology', 'lab/host1'),
        ('runtime', 'private/runtime'), ('output', 'private/output'),
        ('config', 'private/config'), ('docs', 'docs/host1'),
        ('.ai', 'private/.ai'),
        *((name, 'host1/' + name) for name in (
            'knowledge', 'reasoning_agent', 'agent_contract', 'ollama_host',
            'telemetry', 'graph_indexer', 'log_ingestion', 'tools', 'tests')),
    )
    for old, new in mappings:
        if value == old or value.startswith(old + '/'):
            value = new + value[len(old):]
            break
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Evidence path outside project')
    return path


def ref(path):
    path = local_path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def canonical_references(value):
    """Compare frozen contexts using resolved paths, retaining every other field."""
    if isinstance(value, list):
        return [canonical_references(item) for item in value]
    if isinstance(value, dict):
        return {key: (local_path(item).relative_to(ROOT).as_posix()
                      if key in ('path', 'source_path') and 'sha256' in value
                      else canonical_references(item)) for key, item in value.items()}
    return value


def verify(path, expected):
    path = local_path(path)
    if sha(path) != expected:
        raise ValueError('Evidence hash mismatch: ' + str(path))
    return path


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Evidence timestamp lacks timezone')
    return result


def pointer(document, value):
    result = document
    for key in value.lstrip('/').split('/'):
        result = result[key.replace('~1', '/').replace('~0', '~')]
    return result


def context(graph_path, inventory_path, link):
    graph_path = local_path(graph_path)
    graph = read(graph_path)
    meta = graph['graph']
    snapshot_path = verify(meta['snapshot'], meta['snapshot_sha256'])
    inventory_path = verify(inventory_path, meta['inventory_sha256'])
    snapshot, inventory = read(snapshot_path), read(inventory_path)
    if snapshot['lab'] != meta['lab'] or inventory['lab_name'] != meta['lab']:
        raise ValueError('Lab identity mismatch')
    if any(meta[key] != snapshot[key] for key in ('started_at', 'completed_at')):
        raise ValueError('Graph and snapshot times disagree')
    expected = next((x for x in inventory['links'] if x['id'] == link), None)
    if expected is None:
        raise ValueError('Unknown focus link: ' + link)
    routers = {e['router'] for e in expected['endpoints']}
    protocol = 'ospf' if expected['protocol'] == 'ospf' else 'bgp'
    nodes = {n['id']: n for n in graph['nodes']}
    if len(nodes) != len(graph['nodes']):
        raise ValueError('Duplicate graph node IDs')
    edges = graph['edges']
    if any(e['source'] not in nodes or e['target'] not in nodes for e in edges):
        raise ValueError('Dangling graph edge')
    physical = [e for e in edges if e['kind'] == 'physical' and e['link_id'] == link]
    sessions = [e for e in edges if e['kind'] == protocol and e.get('link_id') == link]
    if len(physical) != 2 or len(sessions) != 2:
        raise ValueError('Expected two directed link/session observations')
    if len({e['state'] for e in physical}) != 1:
        raise ValueError('Conflicting physical graph states')
    interfaces = [nodes['interface:' + e['router'] + ':' + e['interface']] for e in expected['endpoints']]
    observations = []
    # Include r1 routes for cross-AS reachability context even when it is not an endpoint.
    for router in sorted(routers | {'r1'}):
        for kind, source in snapshot['routers'][router]['sources'].items():
            observations.append(dict(router=router, source=kind, observation=source,
                evidence=dict(**ref(snapshot_path), pointer=f'/routers/{router}/sources/{kind}')))
    for item in interfaces + sessions:
        evidence = item['evidence']
        if local_path(evidence['snapshot']) != snapshot_path:
            raise ValueError('Graph evidence references another snapshot')
        source = pointer(snapshot, evidence['pointer'])
        if source['status'] == 'ok':
            data = source['data']
            if item['kind'] == 'interface':
                actual = next((x for x in data if x['name'] == item['name']), None)
                if actual != item['observed']:
                    raise ValueError('Interface graph differs from telemetry')
            else:
                records = data['peers'] if protocol == 'bgp' else data
                key = 'address' if protocol == 'bgp' else 'peer_address'
                matches = [x for x in records if x.get(key) == item['peer_address']]
                state = matches[0]['state'] if matches else 'absent'
                if matches != item['observed'] or state != item['state']:
                    raise ValueError('Protocol graph differs from telemetry')
    flags = [n['observed'].get(key) if n['observed'] else None for n in interfaces
             for key in ('admin_up', 'lower_up')]
    actual_state = 'down' if False in flags else ('up' if all(v is True for v in flags) else 'unknown')
    if physical[0]['state'] != actual_state:
        raise ValueError('Physical graph state differs from interfaces')
    manifest = {}
    for entry in meta['log_inputs']:
        path = verify(entry['path'], entry['sha256'])
        manifest[path] = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    lower, upper = (instant(meta['correlation'][key]) for key in ('window_start', 'window_end'))
    if upper != instant(snapshot['completed_at']) or lower > upper:
        raise ValueError('Invalid correlation window')
    logs, omitted = [], 0
    for node in nodes.values():
        if node['kind'] != 'log_event':
            continue
        event = node['event']
        if not lower <= instant(event['event_timestamp']) <= upper:
            raise ValueError('Graph contains out-of-window event')
        citations = []
        for source in node['evidence']:
            path = verify(source['path'], source['sha256'])
            if path not in manifest or source['line'] < 1 or manifest[path][source['line']-1] != event:
                raise ValueError('Graph event differs from frozen log')
            citations.append(dict(**ref(path), line=source['line']))
        if not citations:
            raise ValueError('Uncited log event')
        if event['router'] not in routers or event.get('daemon') != protocol.upper():
            omitted += 1
            continue
        context_edges = [e for e in edges if e['source'] == node['id'] and e['kind'] in
                         ('emitted_by', 'protocol_context', 'temporal_context')]
        if not any(e['kind'] == 'protocol_context' and nodes[e['target']].get('router') == event['router']
                   and nodes[e['target']].get('source') == protocol for e in context_edges):
            raise ValueError('Missing matching protocol context')
        logs.append(dict(graph_node=node['id'], event=event, evidence=citations, graph_edges=context_edges))
    return dict(schema_version=1, focus=dict(link=link, routers=sorted(routers), protocol=protocol),
        inputs=dict(graph=ref(graph_path), snapshot=ref(snapshot_path), inventory=ref(inventory_path),
                    logs=[ref(p) for p in manifest]),
        window=dict(start=meta['correlation']['window_start'], end=meta['correlation']['window_end']),
        collection_status=snapshot['status'], physical=physical, interfaces=interfaces, sessions=sessions,
        telemetry=observations, logs=logs, omitted_other_router_or_protocol_events=omitted,
        semantics='Frozen non-atomic observations; event-time context is not cause. Recent down logs may remain after recovery.')


def retrieve_bundle(graph_path, inventory_path, link, question=None, query_fn=None):
    evidence = context(graph_path, inventory_path, link)
    if query_fn is None:
        from knowledge.retriever import query as query_fn
    protocol = evidence['focus']['protocol']
    state = evidence['physical'][0]['state']
    states = ', '.join(s['state'] for s in evidence['sessions'])
    topic = ('OSPF neighbor adjacency interface link state shortest path routing' if protocol == 'ospf'
             else 'BGP directly connected external peer interface link session reset')
    requests = [('frr', f'{topic}. Observed interface {state}; neighbor states {states}.',
                 [evidence['inputs']['graph'], evidence['inputs']['snapshot']]),
                ('openconfig', 'interface MTU maximum transmission unit admin-status oper-status',
                 [evidence['inputs']['snapshot']])]
    if protocol == 'bgp':
        requests.append(('openconfig', f'BGP neighbor session-state {states}', [evidence['inputs']['snapshot']]))
    # Raw messages are search data only. Keep query length bounded and cite each trigger.
    recent = sorted(evidence['logs'], key=lambda row: instant(row['event']['event_timestamp']), reverse=True)
    for row in recent[:2]:
        requests.append(('frr', topic + '. Log message: ' + row['event']['message'][:500],
                         [dict(graph_node=row['graph_node'], log_citations=row['evidence'])]))
    if question:
        requests.append(('frr', question, []))
    results = []
    for platform, text, refs in requests:
        result = query_fn(text, platform, 5)
        for hit in result['hits']:
            m = hit['metadata']
            source = verify(ROOT / 'host1/knowledge/sources' / m['filename'], m['sha256'])
            lines = source.read_text(encoding='utf-8').splitlines()
            original = f"{m['platform']} {m['document_version']} {m['filename']}\n" + '\n'.join(lines[m['line_start']-1:m['line_end']])
            if original != hit['text'] or m['platform'] != platform:
                raise ValueError('Retrieved citation differs from source/filter')
        results.append(dict(trigger_evidence=refs, retrieval=result, relation='documentation_context',
                            relevance='candidate_not_validated', causal_claim=False))
    bundle = dict(schema_version=1, evidence=evidence, documentation=results,
        diagnosis=None, executable_patch=None,
        limitations=['No automatic root-cause inference or command execution',
                     'Log selection is by endpoint/protocol/time, not proven peer or fault identity',
                     'Topical quality gate is heuristic, not semantic entailment or diagnosis',
                     'Pinned OSPF corpus does not establish MTU-mismatch remediation',
                     'OpenConfig schema is not FRR CLI'])
    from knowledge.quality_gate import assess
    bundle['question'] = question
    bundle['quality_gate'] = assess(bundle, question=question)
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--link', required=True)
    parser.add_argument('--question')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = local_path(args.output)
    if output.exists():
        raise ValueError('Output exists; choose a new evidence filename')
    result = retrieve_bundle(args.graph, args.inventory, args.link, args.question)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(output=str(output), logs=len(result['evidence']['logs']),
                         retrievals=len(result['documentation']))))


if __name__ == '__main__':
    main()
