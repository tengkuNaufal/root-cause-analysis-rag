"""Snapshot collector for the lab; no configuration or remediation commands."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = {
    'interfaces': ['ip', '-j', '-s', 'addr', 'show'],
    'ospf': ['vtysh', '-c', 'show ip ospf neighbor json'],
    'bgp': ['vtysh', '-c', 'show bgp ipv4 unicast summary json'],
    'routes': ['vtysh', '-c', 'show ip route json'],
    'kernel_routes': ['ip', '-j', '-4', 'route', 'show'],
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def require(value, kind):
    if not isinstance(value, kind):
        raise ValueError(f'Expected {kind.__name__}, got {type(value).__name__}')
    return value


def normalize(source, payload):
    """Normalize observed fields only; topology expectations never fill missing data."""
    if source == 'interfaces':
        result = []
        for interface in require(payload, list):
            require(interface, dict)
            flags = require(interface['flags'], list)
            counters = interface.get('stats64', interface.get('stats'))
            result.append({
                'name': interface['ifname'], 'ifindex': interface.get('ifindex'),
                'peer_ifindex': interface.get('link_index'),
                'role': 'management' if interface['ifname'] == 'eth0' else ('loopback' if interface['ifname'] == 'lo' else 'data'),
                'admin_up': 'UP' in flags, 'lower_up': 'LOWER_UP' in flags,
                'operstate': interface.get('operstate'), 'mtu': interface['mtu'],
                'mac': interface.get('address'), 'addresses': require(interface.get('addr_info', []), list),
                'counters': counters,  # Cumulative counters; unavailable is null, not zero.
            })
        return result
    if source == 'ospf':
        neighbors = require(require(payload, dict)['neighbors'], dict)
        return [dict(router_id=router_id, state=n['nbrState'], converged=n.get('converged'),
                     interface=n.get('ifaceName'), peer_address=n.get('ifaceAddress'),
                     uptime_ms=n.get('upTimeInMsec'), dead_timer_remaining_ms=n.get('routerDeadIntervalTimerDueMsec'))
                for router_id, entries in neighbors.items() for n in require(entries, list)]
    if source == 'bgp':
        peers = require(require(payload, dict)['peers'], dict)
        return {'router_id': payload.get('routerId'), 'local_as': payload.get('as'),
                'peers': [dict(address=address, remote_as=p['remoteAs'], state=p['state'],
                               peer_state=p.get('peerState'), uptime_ms=p.get('peerUptimeMsec'),
                               prefixes_received=p.get('pfxRcd'), prefixes_sent=p.get('pfxSnt'),
                               messages_received=p.get('msgRcvd'), messages_sent=p.get('msgSent'),
                               connections_established=p.get('connectionsEstablished'), connections_dropped=p.get('connectionsDropped'))
                          for address, p in peers.items()]}
    if source == 'routes':
        return [dict(prefix=prefix, protocol=r['protocol'], selected=r.get('selected', False),
                     installed=r.get('installed', False), distance=r.get('distance'), metric=r.get('metric'),
                     uptime=r.get('uptime'), nexthops=require(r.get('nexthops', []), list))
                for prefix, entries in require(payload, dict).items() for r in require(entries, list)]
    if source == 'kernel_routes':
        routes = require(payload, list)
        for route in routes:
            require(route, dict)
        return routes
    raise ValueError('Unknown source: ' + source)


def observe(container, source, raw_path, timeout, runner=subprocess.run):
    args = ['docker', 'exec', container, *COMMANDS[source]]
    start, tick = utc_now(), time.monotonic()
    stdout, stderr, code, data, error = '', '', None, None, None
    try:
        result = runner(args, capture_output=True, text=True, timeout=timeout, check=False)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        if code:
            error = {'kind': 'command_failed', 'message': f'Command exited {code}'}
        else:
            try:
                data = normalize(source, json.loads(stdout))
            except (ValueError, TypeError, KeyError) as exc:
                error = {'kind': 'invalid_payload', 'message': str(exc)}
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ''
        stderr = exc.stderr or ''
        stdout = stdout.decode(errors='replace') if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr
        error = {'kind': 'timeout', 'message': f'Exceeded {timeout} seconds'}
    except OSError as exc:
        error = {'kind': 'execution_error', 'message': str(exc)}
    metadata = {'status': 'error' if error else 'ok', 'started_at': start,
                'completed_at': utc_now(), 'duration_seconds': round(time.monotonic() - tick, 6),
                'returncode': code, 'error': error, 'command': args}
    write_json(raw_path, {**metadata, 'stdout': stdout, 'stderr': stderr})
    return {**metadata, 'raw_file': 'raw/' + raw_path.name, 'data': None if error else data}


def collect_router(node, plan, raw_dir, timeout):
    name = node['name']
    container = f'clab-{plan["lab_name"]}-{name}'
    ospf_expected = any(link['protocol'] == 'ospf' and any(e['router'] == name for e in link['endpoints']) for link in plan['links'])
    sources = {}
    for source in COMMANDS:
        if source == 'ospf' and not ospf_expected:
            sources[source] = {'status': 'not_applicable', 'reason': 'No OSPF links assigned in inventory', 'data': None}
        else:
            sources[source] = observe(container, source, raw_dir / f'{name}-{source}.json', timeout)
    return name, {'container': container, 'inventory_asn': node['asn'], 'sources': sources}


def collect_snapshot(plan, directory, timeout=5, workers=6):
    directory.mkdir(parents=True, exist_ok=False)
    raw_dir = directory / 'raw'
    raw_dir.mkdir()
    started, tick = utc_now(), time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        routers = dict(pool.map(lambda node: collect_router(node, plan, raw_dir, timeout), plan['nodes']))
    counts = {key: 0 for key in ('ok', 'error', 'not_applicable')}
    for router in routers.values():
        for source in router['sources'].values():
            counts[source['status']] += 1
    snapshot = {'schema_version': 1, 'lab': plan['lab_name'], 'started_at': started,
                'completed_at': utc_now(), 'duration_seconds': round(time.monotonic() - tick, 6),
                'status': 'partial' if counts['error'] else 'complete', 'source_counts': counts,
                'timestamp_semantics': 'UTC collector observation windows; not router event timestamps; sources are not atomic.',
                'routers': routers}
    # Written only after workers finish; raw evidence remains if collection is interrupted.
    write_json(directory / 'snapshot.json', snapshot)
    return snapshot


def load_plan(path):
    plan = json.loads(path.read_text(encoding='utf-8'))
    names = [n['name'] for n in plan['nodes']]
    if not names or len(set(names)) != len(names):
        raise ValueError('Inventory must have unique, nonempty node names')
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', name) for name in [plan['lab_name'], *names]):
        raise ValueError('Invalid lab/node name')
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, default=ROOT / 'lab/host1/frr/design-plan.json')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'data/host1/telemetry')
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--interval', type=float, default=5, help='Minimum start-to-start seconds; no overlapping cycles')
    parser.add_argument('--timeout', type=float, default=5, help='Per-command timeout seconds')
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    if args.count < 1 or not 1 <= args.workers <= 32 or not math.isfinite(args.timeout) or args.timeout <= 0 or not math.isfinite(args.interval) or args.interval < 0:
        parser.error('Require count>=1, workers=1..32, finite timeout>0 and interval>=0')
    plan = load_plan(args.inventory)
    run_dir = args.output_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / 'inventory.json', plan)
    manifest = {'schema_version': 1, 'started_at': utc_now(), 'status': 'running',
                'requested_count': args.count, 'interval_seconds': args.interval, 'timeout_seconds': args.timeout,
                'workers': args.workers, 'snapshots': []}
    write_json(run_dir / 'manifest.json', manifest)
    try:
        for sequence in range(1, args.count + 1):
            tick = time.monotonic()
            directory = run_dir / f'{sequence:04d}'
            result = collect_snapshot(plan, directory, args.timeout, args.workers)
            manifest['snapshots'].append({'path': f'{sequence:04d}/snapshot.json', 'status': result['status'], 'duration_seconds': result['duration_seconds'], 'source_counts': result['source_counts']})
            write_json(run_dir / 'manifest.json', manifest)
            print(json.dumps({'run': str(run_dir), 'sequence': sequence, **manifest['snapshots'][-1]}), flush=True)
            if sequence < args.count:
                time.sleep(max(0, args.interval - (time.monotonic() - tick)))
        manifest['status'] = 'partial' if any(s['status'] != 'complete' for s in manifest['snapshots']) else 'complete'
    except KeyboardInterrupt:
        manifest['status'] = 'interrupted'
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['error'] = str(exc)
        raise
    finally:
        manifest['completed_at'] = utc_now()
        write_json(run_dir / 'manifest.json', manifest)
    return 0 if manifest['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
