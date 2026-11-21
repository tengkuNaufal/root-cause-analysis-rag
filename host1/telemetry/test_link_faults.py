"""Authorized L12/L35 live fault checks using the actual telemetry collector."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from telemetry.collector import ROOT, collect_snapshot, load_plan, write_json, utc_now


def command(router, *args):
    return subprocess.run(['docker', 'exec', 'clab-rca-' + router, *args], check=True,
                          capture_output=True, text=True, timeout=15).stdout


def inspect(snapshot, case, down):
    def data(router, source):
        return snapshot['routers'][router]['sources'][source]['data']
    ospf = sum(len([n for n in data(f'r{i}', 'ospf') if n['converged'] == 'Full']) for i in range(1, 5))
    bgp = sum(len([n for n in data(f'r{i}', 'bgp')['peers'] if n['state'] == 'Established']) for i in range(1, 7))
    interface = next(i for i in data(case['router'], 'interfaces') if i['name'] == case['interface'])
    peer_interface = next(i for i in data(case['peer_router'], 'interfaces') if i['name'] == case['peer_interface'])
    candidates = [r for r in data('r1', 'routes') if r['prefix'] == case['prefix'] and r['installed']]
    egress = sorted({h['interfaceName'] for r in candidates for h in r['nexthops'] if h.get('fib') and h.get('interfaceName')})
    gateway = sorted({h['ip'] for r in candidates for h in r['nexthops'] if h.get('fib') and h.get('ip')})
    observed = {'ospf_full_endpoint_entries': ospf, 'bgp_established_endpoint_entries': bgp,
                'interface_admin_up': interface['admin_up'], 'interface_lower_up': interface['lower_up'],
                'peer_lower_up': peer_interface['lower_up'], 'mtu': interface['mtu'],
                'r1_target': case['prefix'], 'r1_egress': egress, 'r1_gateway': gateway}
    expected_counts = case['down_counts'] if down else (10, 18)
    expected_route = case['down_route'] if down else case['normal_route']
    checks = [snapshot['status'] == 'complete', (ospf, bgp) == expected_counts,
              interface['admin_up'] == (not down), interface['lower_up'] == (not down),
              peer_interface['lower_up'] == (not down), interface['mtu'] == 1500,
              egress == [expected_route[0]], gateway == [expected_route[1]]]
    if case['id'] == 'L12':
        relations = [any(n['router_id'] == rid and n['converged'] == 'Full' for n in data(router, 'ospf'))
                     for router, rid in [('r1', '10.255.0.2'), ('r2', '10.255.0.1')]]
        observed['affected_ospf_full'] = relations
        checks.append(all(value == (not down) for value in relations))
    else:
        peers = [next(p for p in data(router, 'bgp')['peers'] if p['address'] == ip)
                 for router, ip in [('r3', '10.0.35.2'), ('r5', '10.0.35.1')]]
        observed['affected_bgp'] = peers
        checks.append(all((p['state'] == 'Established') == (not down) for p in peers))
    observed['passed'] = all(checks)
    return observed


def main(run=None):
    plan = load_plan(ROOT / 'lab/host1/frr/design-plan.json')
    run = Path(run) if run is not None else ROOT / 'data/host1/telemetry-faults' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / 'inventory.json', plan)
    events, results = [], []

    def event(action, **details):
        events.append({'time_utc': utc_now(), 'action': action, **details})
        write_json(run / 'events.json', events)
        print(json.dumps(events[-1]), flush=True)

    def baseline(label):
        p = subprocess.run(['python3', str(ROOT / 'lab/host1/frr/verify-runtime.py'), str(run / label)], capture_output=True, text=True, timeout=90)
        (run / (label + '.log')).write_text(p.stdout + p.stderr)
        if p.returncode:
            raise RuntimeError('Baseline failed: ' + label)
        event('baseline_passed', label=label)

    def poll(case, phase, started):
        stable, observations = 0, []
        for seq in range(1, 31):
            snapshot_dir = run / case['id'] / phase / f'{seq:04d}'
            snapshot = collect_snapshot(plan, snapshot_dir)
            try:
                observed = inspect(snapshot, case, phase == 'down')
            except (TypeError, KeyError, StopIteration) as exc:
                observed = {'passed': False, 'error': repr(exc)}
            observed.update(snapshot=str(snapshot_dir.relative_to(run) / 'snapshot.json'),
                            elapsed_seconds=time.monotonic() - started, source_counts=snapshot['source_counts'])
            observations.append(observed)
            write_json(run / case['id'] / (phase + '-observations.json'), observations)
            stable = stable + 1 if observed['passed'] else 0
            if stable >= 2:
                return observed
            if time.monotonic() - started > 60:
                break
            time.sleep(0.5)
        raise RuntimeError('Telemetry did not confirm ' + case['id'] + ' ' + phase)

    cases = [
        {'id': 'L12', 'router': 'r1', 'interface': 'eth1', 'peer_router': 'r2', 'peer_interface': 'eth1',
         'prefix': '10.100.6.1/32', 'normal_route': ('eth1', '10.0.12.2'), 'down_route': ('eth2', '10.0.13.2'), 'down_counts': (8, 18)},
        {'id': 'L35', 'router': 'r3', 'interface': 'eth4', 'peer_router': 'r5', 'peer_interface': 'eth1',
         'prefix': '10.100.5.1/32', 'normal_route': ('eth2', '10.0.13.2'), 'down_route': ('eth1', '10.0.12.2'), 'down_counts': (10, 16)},
    ]
    event('start', evidence=str(run))
    baseline('baseline-before')
    for case in cases:
        directory = run / case['id']
        directory.mkdir()
        before = collect_snapshot(plan, directory / 'before')
        precheck = inspect(before, case, False)
        write_json(directory / 'before-observation.json', precheck)
        if not precheck['passed']:
            raise RuntimeError('Pre-fault telemetry not normal')
        error = None
        result = {'id': case['id'], 'before': precheck}
        try:
            started = time.monotonic()
            event('down_requested', link=case['id'])
            command(case['router'], 'ip', 'link', 'set', 'dev', case['interface'], 'down')
            result['down'] = poll(case, 'down', started)
            event('fault_telemetry_confirmed', link=case['id'], elapsed=result['down']['elapsed_seconds'])
        except BaseException as exc:
            error = exc
        finally:
            started = time.monotonic()
            command(case['router'], 'ip', 'link', 'set', 'dev', case['interface'], 'up')
            event('up_applied', link=case['id'])
        result['restored'] = poll(case, 'restored', started)
        baseline('baseline-after-' + case['id'])
        result['passed'] = error is None
        write_json(directory / 'result.json', result)
        results.append(result)
        if error:
            raise error
    config_equal = {}
    for i in range(1, 7):
        name = f'r{i}-running.conf'
        before = (run / 'baseline-before' / name).read_bytes()
        after = (run / 'baseline-after-L35' / name).read_bytes()
        config_equal[f'r{i}'] = hashlib.sha256(before).hexdigest() == hashlib.sha256(after).hexdigest()
    passed = all(config_equal.values())
    write_json(run / 'summary.json', {'passed': passed, 'scenarios': results, 'running_configs_unchanged': config_equal,
                'scope': 'Two single-trial link faults; confirmation through two consecutive telemetry snapshots. Not precise event/convergence timing.'})
    event('finished', passed=passed, evidence=str(run))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
