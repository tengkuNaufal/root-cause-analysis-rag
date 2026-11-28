"""Fresh read-only collection and frozen, privacy-filtered evidence for live RCA."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from telemetry.collector import collect_snapshot, load_plan
from .models import canonical, digest
from .settings import parse, differences

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT/'lab/host1/frr/design-plan.json'

class CaptureError(ValueError):
    pass

def write(path, value):
    path.write_bytes(canonical(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()

def config_projection(text):
    """Keep diagnostic knobs, never authentication material or local access settings."""
    result=[]
    for raw in text.splitlines():
        line=raw.strip()
        if re.match(r'^(interface |router (?:bgp|ospf) |(?:no )?ip (?:address |ospf |prefix-list )|(?:no )?neighbor |(?:no )?network |route-map |match ip address |set local-preference|shutdown$)',line):
            if re.search(r'password|message-digest-key|authentication-key',line):
                line=re.sub(r'(password|message-digest-key|authentication-key).*',r'\1 [present; redacted]',line)
            result.append(line[:180])
    return result

def network_facts(snapshot, plan):
    """Observed values plus explicit expected inventory; no fault catalog or class hints."""
    facts=[];routers=snapshot['routers'];nodes={n['name']:n for n in plan['nodes']}
    for link in plan['links']:
        endpoints=[];alarm=False
        for ep in link['endpoints']:
            items=routers[ep['router']]['sources']['interfaces']['data']
            found=next((i for i in items if i['name']==ep['interface']),None)
            observed=None if found is None else {
                'mtu':found['mtu'],'admin_up':found['admin_up'],'lower_up':found['lower_up'],
                'ipv4':[a['local']+'/'+str(a['prefixlen']) for a in found['addresses'] if a.get('family')=='inet']}
            bad=observed is None or not observed['admin_up'] or not observed['lower_up'] or observed['mtu']!=link['mtu'] or ep['ipv4'] not in observed['ipv4']
            alarm |= bad
            endpoints.append(dict(router=ep['router'],interface=ep['interface'],expected_ipv4=ep['ipv4'],observed=observed))
        facts.append(dict(type='physical',link=link['id'],expected_mtu=link['mtu'],endpoints=endpoints,anomaly=alarm))
    expected_ospf={r:set() for r in nodes};expected_bgp={r:set() for r in nodes}
    for link in plan['links']:
        a,b=link['endpoints']
        for me,other in ((a,b),(b,a)):
            if link['protocol']=='ospf':expected_ospf[me['router']].add(nodes[other['router']]['router_id'])
            else:expected_bgp[me['router']].add(other['ipv4'].split('/')[0])
    for a,b in plan['ibgp_pairs']:
        expected_bgp[a].add(nodes[b]['router_id']);expected_bgp[b].add(nodes[a]['router_id'])
    services={n['service'] for n in nodes.values()}
    for r,node in nodes.items():
        sources=routers[r]['sources'];ospf=sources['ospf'];bgp=sources['bgp']['data']
        observed_o=[] if ospf['status']=='not_applicable' else [{'id':x['router_id'],'state':x['state']} for x in ospf['data']]
        observed_b=[{'address':x['address'],'remote_as':x['remote_as'],'state':x['state']} for x in bgp['peers']]
        installed={x['prefix'] for x in sources['routes']['data'] if x['installed']}
        missing=sorted(services-installed)
        alarm=(set(x['id'] for x in observed_o)!=expected_ospf[r] or any(not x['state'].startswith('Full') for x in observed_o)
               or set(x['address'] for x in observed_b)!=expected_bgp[r] or any(x['state']!='Established' for x in observed_b) or bool(missing))
        facts.append(dict(type='protocol',router=r,expected_ospf=sorted(expected_ospf[r]),ospf=observed_o,
            expected_bgp=sorted(expected_bgp[r]),bgp=observed_b,missing_services=missing,anomaly=alarm))
    return facts

class ReadOnlyCapture:
    def __init__(self, inventory=INVENTORY, collector=None, runner=None,wall_clock=None):
        self.inventory=Path(inventory);self.collector=collector or collect_snapshot
        self.runner=runner or subprocess.run
        self.wall_clock=wall_clock or (lambda:datetime.now(timezone.utc))

    def readiness(self):
        plan=load_plan(self.inventory)
        names=['clab-rca-'+n['name'] for n in plan['nodes']]
        try:
            p=self.runner(['docker','inspect',*names],capture_output=True,text=True,timeout=5,check=False)
            rows=json.loads(p.stdout) if p.returncode==0 else []
            expected={'/'+n for n in names}
            ok=len(rows)==6 and {r['Name'] for r in rows}==expected and all(r['State']['Running'] and r['Config']['Labels'].get('containerlab')=='rca' for r in rows)
        except (OSError,ValueError,subprocess.TimeoutExpired,KeyError):ok=False
        signature=digest(sorted((r['Name'],r.get('Id',''),r['State'].get('StartedAt','')) for r in rows)) if ok else None
        return {'ready':ok,'reason':None if ok else 'lab_unavailable','runtime_signature':signature,
                'inventory_sha256':hashlib.sha256(self.inventory.read_bytes()).hexdigest()}

    def capture(self, directory):
        if not self.readiness()['ready']:raise CaptureError('lab_unavailable')
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
        start=time.monotonic();plan=load_plan(self.inventory)
        snapshot=self.collector(plan,directory/'telemetry',timeout=3,workers=6)
        if snapshot.get('status')!='complete' or set(snapshot.get('routers',{}))!={n['name'] for n in plan['nodes']}:
            raise CaptureError('partial_capture')
        windows=[]
        for node in plan['nodes']:
            sources=snapshot['routers'][node['name']]['sources']
            for kind in ('interfaces','ospf','bgp','routes','kernel_routes'):
                src=sources.get(kind,{})
                if kind=='ospf' and node['asn']!=65001:
                    if src.get('status')!='not_applicable':raise CaptureError('invalid_applicability')
                    continue
                if src.get('status')!='ok' or src.get('data') is None:raise CaptureError('partial_capture')
                a=datetime.fromisoformat(src['started_at']);b=datetime.fromisoformat(src['completed_at'])
                if a.tzinfo is None or b.tzinfo is None or b<a:raise CaptureError('invalid_capture_window')
                windows.extend((a,b))
        if (max(windows)-min(windows)).total_seconds()>5:raise CaptureError('capture_skew_exceeded')
        facts=network_facts(snapshot,plan)
        baseline_sources={}
        for node in plan['nodes']:
            baseline_path=ROOT/'lab/host1/frr/configs'/node['name']/'frr.conf'
            baseline_sources[node['name']]=hashlib.sha256(baseline_path.read_bytes()).hexdigest()
            p=self.runner(['docker','exec','clab-rca-'+node['name'],'vtysh','-c','show running-config'],
                          capture_output=True,text=True,timeout=3,check=False)
            if p.returncode:raise CaptureError('configuration_capture_failed')
            expected=parse(baseline_path.read_text());observed=parse(p.stdout)
            facts.extend(differences(node['name'],expected,observed))
            write(directory/(node['name']+'-settings.json'),dict(expected=expected,observed=observed))
        finished=time.monotonic()
        # Conservative bound includes all capture commands, not only the last source.
        if finished-start>5:raise CaptureError('capture_skew_exceeded')
        capture_end=self.wall_clock()
        capture_begin=datetime.fromisoformat(snapshot['started_at'])
        if capture_begin.tzinfo is None or capture_end<capture_begin or (capture_end-capture_begin).total_seconds()>6:
            raise CaptureError('clock_changed_during_capture')
        frozen={'observations':facts,'baseline_sources_sha256':baseline_sources,'scope':'Current observations and expected inventory; no ground truth.'}
        sha=write(directory/'facts.json',frozen)
        meta=dict(started_monotonic=start,completed_monotonic=finished,
            capture_started_at=snapshot['started_at'].replace('+00:00','Z'),
            capture_completed_at=capture_end.isoformat().replace('+00:00','Z'),
            inventory_sha256=hashlib.sha256(self.inventory.read_bytes()).hexdigest(),facts_sha256=sha)
        write(directory/'capture.json',meta)
        return dict(facts=frozen,metadata=meta,plan=plan,snapshot=snapshot,directory=directory)
