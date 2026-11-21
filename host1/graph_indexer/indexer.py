"""Build an evidence-bearing NetworkX MultiDiGraph from collector schema v1."""
import argparse
import hashlib
import json
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def interface_id(router, name):
    return f'interface:{router}:{name}'


def build_graph(snapshot, inventory, snapshot_path='snapshot.json'):
    if snapshot.get('schema_version') != 1 or snapshot.get('lab') != inventory['lab_name']:
        raise ValueError('Unsupported snapshot schema or inventory lab mismatch')
    nodes = {n['name']: n for n in inventory['nodes']}
    if len(nodes) != len(inventory['nodes']) or set(snapshot['routers']) - nodes.keys():
        raise ValueError('Duplicate inventory names or unknown snapshot routers')
    graph = nx.MultiDiGraph(schema_version=1, lab=snapshot['lab'],
        snapshot=str(snapshot_path), started_at=snapshot['started_at'],
        completed_at=snapshot['completed_at'], collection_status=snapshot['status'],
        timestamp_semantics='Non-atomic collector observation windows, not event times')

    def source(router, kind):
        return snapshot['routers'].get(router, {}).get('sources', {}).get(kind, {})

    def evidence(router, kind):
        src = source(router, kind)
        return dict(snapshot=str(snapshot_path), pointer=f'/routers/{router}/sources/{kind}',
            raw_file=src.get('raw_file'), status=src.get('status', 'missing'),
            started_at=src.get('started_at'), completed_at=src.get('completed_at'))

    def data(router, kind):
        src = source(router, kind)
        return src.get('data') if src.get('status') == 'ok' else None

    interfaces = {}
    for router, node in nodes.items():
        graph.add_node('router:' + router, kind='router', name=router, inventory=node,
            source_status={k: source(router, k).get('status', 'missing') for k in
                           ('interfaces', 'ospf', 'bgp', 'routes', 'kernel_routes')},
            kernel_routes=data(router, 'kernel_routes'), kernel_evidence=evidence(router, 'kernel_routes'))
        interfaces[router] = {i['name']: i for i in (data(router, 'interfaces') or [])}

    def add_interface(router, name, expected=None):
        iid = interface_id(router, name)
        observed = interfaces[router].get(name)
        graph.add_node(iid, kind='interface', router=router, name=name,
                       observed=observed, expected=expected, evidence=evidence(router, 'interfaces'))
        graph.add_edge('router:' + router, iid, key='owns', kind='owns')
        return iid

    for router in nodes:
        for name in interfaces[router]:
            add_interface(router, name)

    def session(a, b, kind, key, peer_address, link_id=None):
        records = data(a, kind)
        if kind == 'bgp' and records is not None:
            records = records['peers']
        matches = [r for r in (records or []) if
                   (r.get('address') if kind == 'bgp' else r.get('peer_address')) == peer_address]
        state = matches[0]['state'] if matches else ('absent' if records is not None else 'unknown')
        graph.add_edge('router:' + a, 'router:' + b, key=key, kind=kind,
            state=state, healthy=(state == 'Established' if kind == 'bgp' else state.startswith('Full')),
            peer_address=peer_address, link_id=link_id, observed=matches,
            expected=True, evidence=evidence(a, kind))

    for link in inventory['links']:
        endpoints = link['endpoints']
        ids = [add_interface(e['router'], e['interface'], e) for e in endpoints]
        observations = [interfaces[e['router']].get(e['interface']) for e in endpoints]
        flags = [o.get(k) if o else None for o in observations for k in ('admin_up', 'lower_up')]
        state = 'down' if False in flags else ('up' if all(v is True for v in flags) else 'unknown')
        mtus = [o.get('mtu') if o else None for o in observations]
        for i in (0, 1):
            graph.add_edge(ids[i], ids[1-i], key=link['id'], kind='physical',
                link_id=link['id'], state=state, expected=link, observed_mtu=mtus,
                mtu_matches_expected=None if None in mtus else all(m == link['mtu'] for m in mtus),
                evidence=[evidence(e['router'], 'interfaces') for e in endpoints])
            a, b = endpoints[i], endpoints[1-i]
            kind = 'ospf' if link['protocol'] == 'ospf' else 'bgp'
            session(a['router'], b['router'], kind, kind + ':' + link['id'],
                    b['ipv4'].split('/')[0], link['id'])
    for a, b in inventory['ibgp_pairs']:
        session(a, b, 'bgp', 'bgp:ibgp', nodes[b]['router_id'])
        session(b, a, 'bgp', 'bgp:ibgp', nodes[a]['router_id'])

    for router in nodes:
        # Preserve every observed protocol record, including unexpected peers.
        graph.nodes['router:' + router]['protocol_observations'] = {
            k: {'data': data(router, k), 'evidence': evidence(router, k)} for k in ('ospf', 'bgp')}
        for index, route in enumerate(data(router, 'routes') or []):
            rid = f'route:{router}:{route["prefix"]}:{index}'
            prefix = 'prefix:' + route['prefix']
            graph.add_node(rid, kind='route', router=router, **route, evidence=evidence(router, 'routes'))
            graph.add_node(prefix, kind='prefix', prefix=route['prefix'])
            graph.add_edge('router:' + router, rid, key='has_route', kind='has_route')
            graph.add_edge(rid, prefix, key='destination', kind='destination')
            for n, hop in enumerate(route['nexthops']):
                if hop.get('interfaceName'):
                    iid = interface_id(router, hop['interfaceName'])
                    if iid not in graph:
                        add_interface(router, hop['interfaceName'])
                    graph.add_edge(rid, iid, key=f'egress:{n}', kind='egress',
                        installed=route['installed'], fib=hop.get('fib', False), nexthop=hop,
                        evidence=evidence(router, 'routes'))
    return graph


def summarize(graph):
    edges = list(graph.edges(keys=True, data=True))
    links = {d['link_id']: d['state'] for _, _, _, d in edges if d['kind'] == 'physical'}
    sessions = {}
    for kind in ('ospf', 'bgp'):
        directed = {(a, b, key): d for a, b, key, d in edges if d['kind'] == kind}
        # Count healthy unique sessions only when both observations agree.
        sessions[kind] = sum(d['healthy'] and directed.get((b, a, key), {}).get('healthy', False)
                             for (a, b, key), d in directed.items()) // 2
    routes = {}
    for rid, d in graph.nodes(data=True):
        if d['kind'] == 'route' and d['installed']:
            hops = [e['nexthop'] for _, _, e in graph.out_edges(rid, data=True)
                    if e['kind'] == 'egress' and e['fib']]
            routes.setdefault(d['router'], {}).setdefault(d['prefix'], []).extend(hops)
    return dict(nodes=graph.number_of_nodes(), edges=graph.number_of_edges(),
                physical_links=links, healthy_unique_sessions=sessions, installed_egress=routes)


def export(snapshot_path, inventory_path, output):
    graph = build_graph(read(snapshot_path), read(inventory_path), str(snapshot_path))
    graph.graph.update(snapshot_sha256=digest(snapshot_path), inventory_sha256=digest(inventory_path),
                       inventory_path=str(inventory_path), networkx_version=nx.__version__)
    output.mkdir(parents=True, exist_ok=False)
    for filename, value in [('graph.json', nx.node_link_data(graph, edges='edges')),
                            ('summary.json', summarize(graph))]:
        (output / filename).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    graph = export(args.snapshot, args.inventory, args.output)
    print(json.dumps({'nodes': len(graph), 'edges': graph.number_of_edges(), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
