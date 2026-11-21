"""Read-only verification of the running rca lab, plus service-sourced ICMP."""
import concurrent.futures
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
plan = json.loads((root / 'lab/host1/frr/design-plan.json').read_text())
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
nodes = {n['name']: n for n in plan['nodes']}
errors = []

def run(args, file):
    p = subprocess.run(args, capture_output=True, text=True, timeout=20)
    (out / file).write_text(p.stdout)
    if p.stderr:
        (out / (file + '.stderr')).write_text(p.stderr)
    if p.returncode:
        raise RuntimeError(f'{args}: exit {p.returncode}: {p.stderr or p.stdout}')
    return p.stdout

def snapshot(name):
    prefix = ['docker', 'exec', 'clab-rca-' + name]
    data = {}
    commands = {
        'bgp-summary': ['vtysh', '-c', 'show bgp ipv4 unicast summary json'],
        'bgp-table': ['vtysh', '-c', 'show bgp ipv4 unicast json'],
        'routes': ['vtysh', '-c', 'show ip route json'],
        'interfaces': ['ip', '-j', '-4', 'addr', 'show'],
        'kernel-routes': ['ip', '-j', '-4', 'route', 'show'],
    }
    if nodes[name]['asn'] == 65001:
        commands['ospf'] = ['vtysh', '-c', 'show ip ospf neighbor json']
    for key, cmd in commands.items():
        data[key] = json.loads(run(prefix + cmd, f'{name}-{key}.json'))
    run(prefix + ['vtysh', '-c', 'show running-config'], f'{name}-running.conf')
    data['forwarding'] = run(prefix + ['sysctl', '-n', 'net.ipv4.ip_forward'], f'{name}-forwarding.txt').strip()
    return name, data

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    snapshots = dict(pool.map(snapshot, nodes))
# Inspect only status fields, not environment variables or credentials.
status = run(['docker', 'inspect', '--format', '{{.Name}} {{.State.Status}} {{.RestartCount}}'] +
             ['clab-rca-' + n for n in nodes], 'container-status.txt')
if len(status.splitlines()) != 6 or any(' running 0' not in line for line in status.splitlines()):
    errors.append('Container state/restart count differs from clean baseline')
counts = {}
for name, d in snapshots.items():
    n = nodes[name]
    peers_expected = {}
    ospf_expected = set()
    if n['asn'] == 65001:
        peers_expected.update({p['router_id']: p['asn'] for p in nodes.values() if p['asn'] == 65001 and p['name'] != name})
    for link in plan['links']:
        own = next((e for e in link['endpoints'] if e['router'] == name), None)
        if own is None:
            continue
        other = next(e for e in link['endpoints'] if e['router'] != name)
        if link['protocol'] == 'ebgp':
            peers_expected[other['ipv4'].split('/')[0]] = nodes[other['router']]['asn']
        else:
            ospf_expected.add(nodes[other['router']]['router_id'])
        interface = next((i for i in d['interfaces'] if i['ifname'] == own['interface']), {})
        addresses = {a['local'] + '/' + str(a['prefixlen']) for a in interface.get('addr_info', [])}
        if own['ipv4'] not in addresses or interface.get('mtu') != 1500 or not {'UP', 'LOWER_UP'}.issubset(interface.get('flags', [])):
            errors.append(f'{name}:{own["interface"]}: address/MTU/link mismatch')
    peers = d['bgp-summary'].get('peers', {})
    if set(peers) != set(peers_expected) or any(p['state'] != 'Established' or p['remoteAs'] != peers_expected.get(ip) for ip, p in peers.items()):
        errors.append(f'{name}: BGP peer mismatch')
    ospf = d.get('ospf', {}).get('neighbors', {})
    if set(ospf) != ospf_expected or any(x.get('converged') != 'Full' for entries in ospf.values() for x in entries):
        errors.append(f'{name}: OSPF neighbor mismatch')
    services = {p['service'] for p in nodes.values()}
    bgp_prefixes = set(d['bgp-table'].get('routes', {}))
    if bgp_prefixes != services:
        errors.append(f'{name}: unexpected/missing BGP prefixes: {bgp_prefixes ^ services}')
    for service in services:
        if not any(r.get('installed') for r in d['routes'].get(service, [])):
            errors.append(f'{name}: service route not installed: {service}')
    if any(r.get('dst') == 'default' for r in d['kernel-routes']):
        errors.append(f'{name}: management default route still present')
    if d['forwarding'] != '1':
        errors.append(f'{name}: IPv4 forwarding disabled')
    counts[name] = {'ospf_full': sum(len(v) for v in ospf.values()), 'bgp_established': len(peers), 'bgp_prefixes': len(bgp_prefixes)}

def probe(pair):
    src, dst = pair
    source_ip = nodes[src]['service'].split('/')[0]
    dest_ip = nodes[dst]['service'].split('/')[0]
    prefix = ['docker', 'exec', 'clab-rca-' + src]
    route = json.loads(run(prefix + ['ip', '-j', 'route', 'get', dest_ip, 'from', source_ip], f'{src}-to-{dst}-route-get.json'))
    p = subprocess.run(prefix + ['ping', '-n', '-I', source_ip, '-c', '4', '-i', '0.2', '-W', '2', '-w', '6', dest_ip], capture_output=True, text=True, timeout=12)
    (out / f'{src}-to-{dst}-ping.txt').write_text(p.stdout + p.stderr)
    match = re.search(r'(\d+) packets transmitted, (\d+)(?: packets)? received', p.stdout)
    sent, received = map(int, match.groups()) if match else (0, 0)
    dev = route[0].get('dev') if route else None
    return {'source': src, 'destination': dst, 'sent': sent, 'received': received,
            'egress': dev, 'passed': p.returncode == 0 and sent == received == 4 and dev not in (None, 'eth0', 'lo')}

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    probes = list(pool.map(probe, [(a, b) for a in nodes for b in nodes if a != b]))
errors.extend(f'Ping/route failed: {p["source"]}->{p["destination"]}' for p in probes if not p['passed'])
result = {'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'passed': not errors, 'routers': counts, 'ospf_unique_adjacencies': sum(x['ospf_full'] for x in counts.values()) // 2,
          'bgp_unique_sessions': sum(x['bgp_established'] for x in counts.values()) // 2,
          'probes_passed': sum(p['passed'] for p in probes), 'probes_total': len(probes),
          'packets_sent': sum(p['sent'] for p in probes), 'packets_received': sum(p['received'] for p in probes),
          'probes': probes, 'errors': errors, 'scope': 'Baseline only; no fault injection or failover test.'}
(out / 'verification-summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'probes'}, indent=2))
sys.exit(bool(errors))
