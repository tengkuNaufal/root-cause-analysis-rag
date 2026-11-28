"""Check model proposals against frozen measurements. Never generate or execute commands."""
from .settings import area, supports


class RepairError(ValueError):
    pass


def actions(result):
    events=[]
    for cmd in result.proposed_patch:
        iface=None;asn=None;family=None
        if cmd.interpreter=='linux_argv':
            words=cmd.arguments
            if words[:3]==['ip','link','set']:
                rest=words[3:];rest=rest[1:] if rest[:1]==['dev'] else rest
                if len(rest)>=2:events.append((cmd.router,rest[0],None,None,' '.join(rest[1:])))
            continue
        for raw in cmd.arguments:
            line=' '.join(raw.split())
            if line in ('configure terminal','conf t','end'):
                iface=None;asn=None;family=None
            elif line.startswith('interface '):iface=line.split()[1];asn=None;family=None
            elif line.startswith('router bgp '):asn=int(line.split()[2]);iface=None;family=None
            elif line.startswith('address-family '):family=' '.join(line.split()[1:])
            elif line=='exit-address-family':family=None
            elif line in ('exit','quit'):iface=None;family=None
            else:events.append((cmd.router,iface,asn,family,line))
    return events


def validate_repair(capture,result):
    """A valid diagnosis does not imply its patch repairs the observed setting."""
    if result.status!='hypothesis' or not result.proposed_patch:return
    cause=result.root_cause_class;router=result.root_cause_router
    facts=capture['facts']['observations'];events=actions(result)
    def require(ok):
        if not ok:raise RepairError('proposal_does_not_restore_observed_baseline')
    def lines(iface=None,asn=None):
        return [line for r,i,a,_,line in events if r==router and i==iface and a==asn]
    if cause in ('mtu_mismatch','link_down'):
        targets=[(ep,f) for f in facts if f['type']=='physical' for ep in f['endpoints']
                 if ep['router']==router and ep.get('observed') and
                 (not ep['observed']['admin_up'] if cause=='link_down' else ep['observed']['mtu']!=f['expected_mtu'])]
        require(bool(targets))
        for ep,f in targets:
            require(('up' if cause=='link_down' else 'mtu '+str(f['expected_mtu'])) in lines(ep['interface']))
        return
    relevant=[f for f in facts if f.get('router')==router and supports(cause,f)]
    require(bool(relevant))
    for fact in relevant:
        key=fact['key'];expected=fact['expected'];observed=fact['observed']
        if key.startswith('interface/'):
            iface=key.split('/')[1];ls=lines(iface)
            if cause=='ospf_hello_mismatch':require('ip ospf hello-interval '+str(expected) in ls)
            elif cause=='ospf_area_mismatch':
                require(expected is not None)
                old=[n for n,l in enumerate(ls) if l.startswith('no ip ospf area ') and area(l.split()[-1])==area(str(observed))] if observed is not None else [-1]
                new=[n for n,l in enumerate(ls) if l.startswith('ip ospf area ') and area(l.split()[-1])==area(str(expected))]
                require(bool(old and new) and min(old)<max(new))
                last=next((l for l in reversed(ls) if l.startswith(('ip ospf area ','no ip ospf area '))),None)
                require(last is not None and last.startswith('ip ospf area ') and area(last.split()[-1])==area(str(expected)))
            elif cause=='ospf_auth_mismatch':
                # Secrets are never captured or invented. Only the no-auth baseline is repairable here.
                auth=next((f['expected'] for f in relevant if f['key'].endswith('/ospf_authentication')),None)
                auth_lines=[l for l in ls if l.startswith(('ip ospf authentication','no ip ospf authentication'))]
                require(auth is None and bool(auth_lines) and auth_lines[-1]=='no ip ospf authentication')
                require(not any(l.startswith('ip ospf message-digest-key ') for l in ls))
                if key.endswith('/ospf_key_ids'):
                    require(not expected)
                    require(all('no ip ospf message-digest-key '+str(i) in ls for i in observed or []))
                if key.endswith('/ospf_key_present') and observed and not expected:
                    ids=next((f['observed'] for f in relevant if f['key']==key.removesuffix('present')+'ids'),None)
                    require(bool(ids))
            elif cause=='wrong_ip_address':
                require(all('no ip address '+a in ls for a in set(observed or [])-set(expected or [])))
                require(all('ip address '+a in ls for a in set(expected or [])-set(observed or [])))
        elif cause in ('bgp_neighbor_shutdown','bgp_wrong_remote_as','bgp_missing_network'):
            asn=fact.get('configuration_context',{}).get('expected_bgp_asn');require(asn is not None)
            ls=lines(asn=asn)
            if cause=='bgp_neighbor_shutdown':require('no neighbor '+key.split('/')[1]+' shutdown' in ls)
            elif cause=='bgp_wrong_remote_as':require('neighbor '+key.split('/')[1]+' remote-as '+str(expected) in ls)
            else:
                for prefix in set(expected or [])-set(observed or []):
                    require(any(r==router and a==asn and family in ('ipv4','ipv4 unicast') and line=='network '+prefix
                                for r,_,a,family,line in events))
        elif cause=='bgp_inbound_filter':
            # Support removal of newly observed entries only. Existing policy replacement needs more context.
            require(expected is None)
            bits=key.split('/');ls=lines()
            if bits[0]=='route_map':require('no route-map '+' '.join(bits[1:]) in ls)
            elif bits[0]=='prefix_list':
                empty_baseline=fact.get('configuration_context',{}).get('baseline_policy_entries')==[]
                require('no ip prefix-list '+' '.join(bits[1:]) in ls or
                        (empty_baseline and 'no ip prefix-list '+bits[1] in ls))
