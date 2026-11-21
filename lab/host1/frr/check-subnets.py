"""Compare the plan with saved Windows/WSL/Docker IPv4 inventories."""
import ipaddress
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
evidence = Path(sys.argv[1]).resolve()
plan = json.loads((root / 'lab/host1/frr/design-plan.json').read_text())
targets = {ipaddress.ip_network(plan['management']['subnet'])}
for node in plan['nodes']:
    targets.update(ipaddress.ip_network(node[key]) for key in ('loopback', 'service'))
for link in plan['links']:
    targets.add(ipaddress.ip_interface(link['endpoints'][0]['ipv4']).network)
observed = []
for entry in json.loads((evidence / 'windows-routes.json').read_text(encoding='utf-8-sig')):
    observed.append(('Windows', entry['DestinationPrefix']))
for entry in json.loads((evidence / 'wsl-routes.json').read_text()):
    observed.append(('WSL', entry.get('dst', 'default')))
for entry in json.loads((evidence / 'docker-networks.json').read_text()):
    for config in entry.get('IPAM', {}).get('Config') or []:
        if config.get('Subnet'):
            observed.append(('Docker:' + entry['Name'], config['Subnet']))
conflicts = []
for source, prefix in observed:
    if prefix in ('default', '0.0.0.0/0'):
        continue
    network = ipaddress.ip_network(prefix, strict=False)
    if network.version != 4:
        continue
    for target in targets:
        if target.overlaps(network):
            conflicts.append({'source': source, 'existing': str(network), 'planned': str(target)})
result = {'passed': not conflicts, 'planned_subnets_checked': len(targets),
          'conflicts': conflicts, 'scope': 'Saved active route tables and Docker networks; excludes default routes, does not predict future VPN routes.'}
(evidence / 'subnet-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
sys.exit(bool(conflicts))
