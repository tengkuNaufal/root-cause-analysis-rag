"""Explicit link-state RCA hypothesis profile, preserving the existing integrity gate."""
import re
from knowledge.evidence import ROOT, read, verify, ref, instant
from knowledge.quality_gate import assess_context

VERSION = 'link-rca-1.0'

def mechanism(protocol):
    """Select a small, exact passage from already frozen primary sources."""
    if protocol == 'ospf':
        registry = ROOT / 'host1/knowledge/supplemental-mtu/manifest.json'
        entry = next(e for e in read(registry) if e['filename'] == 'rfc2328.txt')
        path = verify(registry.parent / entry['filename'], entry['sha256'])
        url = entry['url']
        lines = path.read_text().splitlines()
        start = next(i for i, line in enumerate(lines) if 'Event:  InterfaceDown' in line)
        end = next(i for i in range(start, start + 20) if 'associated neighbors (see Section 10.2)' in lines[i]) + 1
    elif protocol == 'bgp':
        registry = ROOT / 'host1/knowledge/sources-manifest.json'
        entry = next(e for e in read(registry) if e['filename'] == 'frr-bgp.rst')
        path = verify(ROOT / 'host1/knowledge/sources' / entry['filename'], entry['sha256'])
        url = entry['source_url']
        lines = path.read_text().splitlines()
        start = lines.index('.. clicmd:: bgp fast-external-failover')
        end = next(i for i in range(start + 2, start + 20) if not lines[i].strip())
    else:
        raise ValueError('unsupported_protocol')
    text = '\n'.join(lines[start:end])
    locator = f'{url}#L{start+1}-L{end}' if protocol=='bgp' else f'{url};local_lines={start+1}:{end}'
    return dict(id='D1', kind='documentation', source_path=path.relative_to(ROOT).as_posix(),
                sha256=entry['sha256'], locator=locator, content=text,
                registry=ref(registry), line_start=start+1, line_end=end)

def state_scope(e):
    """Admit a narrow supported state; do not provide an answer to the model."""
    nodes, sessions = e['interfaces'], e['sessions']
    if len(nodes) != 2 or len(sessions) != 2:
        raise ValueError('incomplete_endpoint_context')
    flags = [n['observed'] for n in nodes]
    if any(o is None or type(o.get('admin_up')) is not bool or type(o.get('lower_up')) is not bool for o in flags):
        raise ValueError('unknown_interface_state')
    if any(type(o.get('mtu')) is not int or o['mtu']<=0 for o in flags):
        raise ValueError('unknown_mtu')
    if flags[0].get('mtu') != flags[1].get('mtu'):
        raise ValueError('mtu_mismatch_outside_link_rca_profile')
    protocol = e['focus']['protocol']
    healthy = [s['state'].startswith('Full') if protocol == 'ospf' else s['state'] == 'Established' for s in sessions]
    physical = e['physical'][0]['state']
    if physical == 'up' and all(o['admin_up'] and o['lower_up'] for o in flags) and all(healthy):
        return 'coherent_up_context'
    if (physical == 'down' and sum(not o['admin_up'] for o in flags) == 1
            and all(not o['lower_up'] for o in flags) and not any(healthy)):
        states = {s['state'] for s in sessions}
        if (protocol == 'ospf' and states != {'absent'}) or (protocol == 'bgp' and not states <= {'Active','Idle','Connect'}):
            raise ValueError('unsupported_protocol_failure_state')
        return 'coherent_admin_down_context'
    raise ValueError('ambiguous_or_conflicting_link_state')

def scoped_events(e):
    """Select only peer/interface-specific transitions, not generic router errors."""
    output = []
    protocol = e['focus']['protocol']
    interfaces = {n['router']: n['name'] for n in e['interfaces']}
    sessions = {s['source'].split(':', 1)[1]: s for s in e['sessions']}
    for row in e['logs']:
        event = row['event']; router = event['router']
        if router not in sessions:
            continue
        peer = sessions[router]['peer_address']; message = event['message']
        if protocol == 'ospf':
            marker = f'NbrIP {peer} (default) on {interfaces[router]}:'
            if marker not in message or 'AdjChg:' not in message:
                continue
            if 'Full -> Deleted (KillNbr)' in message:
                transition = 'down'
            elif '-> Full (' in message:
                transition = 'up'
            else:
                continue
        else:
            if not re.search(r'neighbor ' + re.escape(peer) + r'(?:\(|\s)', message):
                continue
            if ' Down Interface down' in message:
                transition = 'down'
            elif message.endswith(' Up'):
                transition = 'up'
            else:
                continue
        output.append(dict(row=row, transition=transition))
    return sorted(output, key=lambda r: instant(r['row']['event']['event_timestamp']))

def assess_rca(bundle, mode='replay', as_of=None):
    # Keep all source/hash/citation/completeness/freshness checks from the old
    # gate. Its topical heuristic is superseded only by the exact primary-source
    # mechanism check below, not by a blanket free-question exception.
    base = assess_context(bundle, mode=mode, as_of=as_of)
    reasons = [r for r in base['reasons'] if r != 'no_topically_relevant_verified_documentation']
    result = dict(gate_version=VERSION, decision='abstain', answer_supported=False,
                  hypothesis_allowed=False, diagnosis_allowed=False, execution_allowed=False,
                  mode=mode, reasons=reasons, integrity_gate=base,
                  scope='operational_link_state_only_not_actor_or_remediation')
    try:
        doc = mechanism(bundle['evidence']['focus']['protocol'])
        result['mechanism'] = doc
        scope = state_scope(bundle['evidence'])
        result['admissible_context'] = scope
        events = scoped_events(bundle['evidence'])
        result['matching_transitions'] = dict(down=sum(x['transition']=='down' for x in events),
                                              up=sum(x['transition']=='up' for x in events))
        if scope == 'coherent_admin_down_context':
            routers = {x['row']['event']['router'] for x in events if x['transition']=='down'}
            if routers != set(bundle['evidence']['focus']['routers']):
                reasons.append('missing_peer_specific_down_transition')
    except (ValueError, KeyError, TypeError, StopIteration, OSError) as exc:
        reasons.append('unsupported_or_invalid_rca_context:' + str(exc))
    if not reasons:
        result.update(decision='context_ready', answer_supported=True, hypothesis_allowed=True)
    return result
