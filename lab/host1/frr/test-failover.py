"""Two explicit lab link-down tests; always restore the touched endpoint."""
import concurrent.futures
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'data/host1/frr-failover' / datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
OUT.mkdir(parents=True, exist_ok=False)
PLAN = json.loads((ROOT / 'lab/host1/frr/design-plan.json').read_text())
OWNERS = {e['ipv4'].split('/')[0]: e['router'] for l in PLAN['links'] for e in l['endpoints']}
EVENTS = []

def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15, check=True).stdout

def node(name, *args):
    return command(['docker', 'exec', 'clab-rca-' + name, *args])

def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def event(action, **fields):
    record = {'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'action': action, **fields}
    EVENTS.append(record)
    save(OUT / 'events.json', EVENTS)
    print(json.dumps(record), flush=True)

def baseline(label):
    result = subprocess.run(['python3', str(ROOT / 'lab/host1/frr/verify-runtime.py'), str(OUT / label)], capture_output=True, text=True, timeout=90)
    (OUT / (label + '.log')).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Baseline verification failed: ' + label)
    event('baseline_passed', label=label)

def path_to(dest):
    path, routes = ['r1'], []
    current = 'r1'
    for _ in range(6):
        if current == dest:
            return path, routes
        route = json.loads(node(current, 'ip', '-j', 'route', 'get', f'10.100.{dest[1:]}.1'))[0]
        routes.append({'router': current, 'route': route})
        current = OWNERS.get(route.get('gateway'))
        if current is None or current in path or route.get('dev') == 'eth0':
            raise RuntimeError('Incomplete or looping path: ' + repr(routes))
        path.append(current)
    raise RuntimeError('Too many hops')

def protocols(directory=None):
    def snap(name):
        bgp = json.loads(node(name, 'vtysh', '-c', 'show bgp ipv4 unicast summary json'))
        ospf = json.loads(node(name, 'vtysh', '-c', 'show ip ospf neighbor json')) if int(name[1:]) <= 4 else {'neighbors': {}}
        if directory:
            save(directory / (name + '-bgp.json'), bgp)
            save(directory / (name + '-ospf.json'), ospf)
            (directory / (name + '-routes.json')).write_text(node(name, 'vtysh', '-c', 'show ip route json'))
        return sum(p['state'] == 'Established' for p in bgp['peers'].values()), sum(x.get('converged') == 'Full' for a in ospf['neighbors'].values() for x in a)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        counts = list(pool.map(snap, [f'r{i}' for i in range(1, 7)]))
    return {'bgp_endpoint_entries': sum(c[0] for c in counts), 'ospf_endpoint_entries': sum(c[1] for c in counts)}

def wait_state(dest, expected_path, expected_counts, started, directory, phase):
    observations, stable = [], 0
    while time.monotonic() - started < 60:
        try:
            path, routes = path_to(dest)
            counts = protocols()
            ping = node('r1', 'ping', '-n', '-I', '10.100.1.1', '-c', '1', '-W', '1', f'10.100.{dest[1:]}.1')
            ok = path == expected_path and counts == expected_counts
            observation = {'elapsed_seconds': time.monotonic() - started, 'path': path, 'counts': counts, 'passed': ok}
            stable = stable + 1 if ok else 0
            if stable >= 3:
                observations.append(observation)
                save(directory / (phase + '-polls.json'), observations)
                save(directory / (phase + '-path.json'), {'path': path, 'route_get_per_hop': routes})
                (directory / (phase + '-probe.txt')).write_text(ping)
                return observation['elapsed_seconds']
        except (subprocess.SubprocessError, ValueError, KeyError, RuntimeError) as exc:
            observation = {'elapsed_seconds': time.monotonic() - started, 'passed': False, 'error': str(exc)}
            stable = 0
        observations.append(observation)
        save(directory / (phase + '-polls.json'), observations)
        time.sleep(0.25)
    raise RuntimeError(phase + ' did not converge within 60 seconds')

def scenario(link, router, interface, dest, normal, alternate, down_counts):
    directory = OUT / link
    directory.mkdir()
    observed, _ = path_to(dest)
    if observed != normal:
        raise RuntimeError('Unexpected baseline path: ' + repr(observed))
    monitor_file = (directory / 'transition-ping.txt').open('w')
    monitor = subprocess.Popen(['docker', 'exec', 'clab-rca-r1', 'ping', '-n', '-I', '10.100.1.1', '-c', '60', '-i', '0.2', '-W', '1', '-w', '18', f'10.100.{dest[1:]}.1'], stdout=monitor_file, stderr=subprocess.STDOUT)
    result = {'link': link, 'router': router, 'interface': interface, 'normal_path': normal, 'expected_alternate_path': alternate}
    try:
        time.sleep(0.5)
        started = time.monotonic()
        event('link_down_requested', link=link, router=router, interface=interface)
        node(router, 'ip', 'link', 'set', 'dev', interface, 'down')
        (directory / 'interface-down.json').write_text(node(router, 'ip', '-j', 'link', 'show', 'dev', interface))
        result['failover_confirmed_seconds'] = wait_state(dest, alternate, down_counts, started, directory, 'down')
        result['down_protocols'] = protocols(directory)
        monitor.wait(timeout=20)
        result['transition_ping_exit'] = monitor.returncode
        result['fault_passed'] = True
        event('alternate_path_confirmed', link=link, seconds=result['failover_confirmed_seconds'], path=alternate)
    finally:
        # Even a failed observation restores the endpoint before propagating errors.
        restored_at = time.monotonic()
        node(router, 'ip', 'link', 'set', 'dev', interface, 'up')
        event('link_up_applied', link=link)
        if monitor.poll() is None:
            monitor.wait(timeout=20)
        monitor_file.close()
        save(directory / 'result.json', result)
    result['recovery_confirmed_seconds'] = wait_state(dest, normal, {'bgp_endpoint_entries': 18, 'ospf_endpoint_entries': 10}, restored_at, directory, 'restored')
    baseline('after-' + link)
    result['restored_baseline_passed'] = True
    save(directory / 'result.json', result)
    event('restored_baseline_passed', link=link, seconds=result['recovery_confirmed_seconds'])
    return result

event('start', evidence=str(OUT))
baseline('before')
results = []
try:
    results.append(scenario('L12', 'r1', 'eth1', 'r6', ['r1', 'r2', 'r4', 'r6'], ['r1', 'r3', 'r4', 'r6'], {'bgp_endpoint_entries': 18, 'ospf_endpoint_entries': 8}))
    results.append(scenario('L35', 'r3', 'eth4', 'r5', ['r1', 'r3', 'r5'], ['r1', 'r2', 'r4', 'r6', 'r5'], {'bgp_endpoint_entries': 16, 'ospf_endpoint_entries': 10}))
except BaseException as exc:
    event('failed', error=str(exc))
    raise
save(OUT / 'summary.json', {'passed': True, 'scenarios': results, 'timing_note': 'Wall-clock upper bound from link command request through three consecutive successful polling cycles (path, protocol counts, ping); not precise convergence or RCA latency.'})
event('all_passed', evidence=str(OUT))
