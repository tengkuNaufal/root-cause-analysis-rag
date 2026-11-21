"""Verify a healthy six-router telemetry run against its archived inventory."""
from datetime import datetime
import json
from pathlib import Path
import sys

run = Path(sys.argv[1])
plan = json.loads((run / 'inventory.json').read_text())
manifest = json.loads((run / 'manifest.json').read_text())
checks, errors = [], []
for entry in manifest['snapshots']:
    path = run / entry['path']
    snapshot = json.loads(path.read_text())
    data_count = ospf_count = bgp_count = 0
    try:
        assert snapshot['status'] == 'complete'
        assert len(snapshot['routers']) == len(plan['nodes']) == 6
        for n in plan['nodes']:
            sources = snapshot['routers'][n['name']]['sources']
            for source in sources.values():
                if source['status'] == 'not_applicable':
                    continue
                assert source['status'] == 'ok'
                assert datetime.fromisoformat(snapshot['started_at']) <= datetime.fromisoformat(source['started_at']) <= datetime.fromisoformat(source['completed_at']) <= datetime.fromisoformat(snapshot['completed_at'])
                raw = json.loads((path.parent / source['raw_file']).read_text())
                assert raw['returncode'] == 0
                json.loads(raw['stdout'])
            interfaces = {i['name']: i for i in sources['interfaces']['data']}
            for link in plan['links']:
                for endpoint in link['endpoints']:
                    if endpoint['router'] != n['name']:
                        continue
                    i = interfaces[endpoint['interface']]
                    assert i['mtu'] == link['mtu'] and i['admin_up'] and i['lower_up']
                    assert endpoint['ipv4'] in {a['local'] + '/' + str(a['prefixlen']) for a in i['addresses']}
                    assert all(i['counters'][direction][key] >= 0 for direction in ('rx', 'tx') for key in ('bytes', 'packets', 'errors', 'dropped'))
                    data_count += 1
            if n['asn'] == 65001:
                neighbors = sources['ospf']['data']
                assert all(x['converged'] == 'Full' for x in neighbors)
                ospf_count += len(neighbors)
            else:
                assert sources['ospf']['status'] == 'not_applicable'
            peers = sources['bgp']['data']['peers']
            assert all(p['state'] == 'Established' for p in peers)
            bgp_count += len(peers)
            installed = {r['prefix'] for r in sources['routes']['data'] if r['installed']}
            assert {p['service'] for p in plan['nodes']} <= installed
            assert not any(r.get('dst') == 'default' for r in sources['kernel_routes']['data'])
        assert (data_count, ospf_count, bgp_count) == (16, 10, 18)
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        errors.append({'snapshot': entry['path'], 'error': str(exc) or 'Baseline assertion failed'})
    checks.append({'snapshot': entry['path'], 'data_interfaces': data_count,
                   'ospf_full_endpoint_entries': ospf_count, 'bgp_established_endpoint_entries': bgp_count,
                   'duration_seconds': snapshot['duration_seconds']})
assert manifest['status'] == 'complete' and len(checks) == manifest['requested_count']
result = {'passed': not errors, 'checks': checks, 'errors': errors,
          'scope': 'Healthy live run, no fault injection. Transport failure handling tested separately with unit tests.'}
(run / 'live-validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
sys.exit(bool(errors))
