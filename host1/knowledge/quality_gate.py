"""Conservative, explainable context gate. Passing never authorizes diagnosis or CLI."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from knowledge.evidence import ROOT, canonical_references, context, instant, local_path, read, ref, verify

VERSION = '2.1'
SUPPORTED = {'network_context', 'interface_mtu_definition', 'bgp_session_state'}


def citation(hit, platform):
    m = hit['metadata']
    manifest = read(ROOT / 'host1/knowledge/sources-manifest.json')
    source = next((s for s in manifest if s['filename'] == m['filename']), None)
    if source is None or any(m.get(k) != source[k] for k in
                             ('platform', 'sha256', 'source_url', 'document_version', 'content_kind')):
        raise ValueError('Citation metadata differs from source manifest')
    if m['platform'] != platform:
        raise ValueError('Wrong platform')
    path = verify(ROOT / 'host1/knowledge/sources' / m['filename'], m['sha256'])
    lines = path.read_text(encoding='utf-8').splitlines()
    a, b = m['line_start'], m['line_end']
    if not isinstance(a, int) or not isinstance(b, int) or not 1 <= a <= b <= len(lines):
        raise ValueError('Invalid citation lines')
    text = f"{m['platform']} {m['document_version']} {m['filename']}\n" + '\n'.join(lines[a-1:b])
    ident = hashlib.sha256(f"{m['sha256']}:{a}:{b}".encode()).hexdigest()
    if (text != hit['text'] or hit['id'] != ident or
        m['citation_url'] != m['source_url'] + f'#L{a}-L{b}' or
        m['content_sha256'] != hashlib.sha256(text.encode()).hexdigest()):
        raise ValueError('Citation text, ID, URL or content hash mismatch')


def relevant(hit, intent, protocol):
    """Explicit topic rules, not a calibrated relevance probability or entailment test."""
    m = hit['metadata']
    text = hit['text'].split('\n', 1)[-1].lower()
    if intent == 'interface_mtu_definition':
        ok = m['platform'] == 'openconfig' and bool(re.search(r'leaf\s+mtu\s*\{', text))
        return ok, 'requires_openconfig_leaf_mtu'
    if intent == 'bgp_session_state':
        ok = m['platform'] == 'openconfig' and bool(re.search(r'leaf\s+session-state\s*\{', text))
        return ok, 'requires_openconfig_leaf_session_state'
    if intent == 'network_context':
        # Schema hits cannot satisfy the FRR protocol-documentation requirement.
        terms = ('neighbor', 'adjacen', 'interface') if protocol == 'ospf' else ('peer', 'neighbor', 'session')
        count = sum(t in text for t in terms)
        ok = (m['platform'] == 'frr' and m['content_kind'] == 'cli_documentation'
              and bool(re.search(r'\b' + protocol + r'\b', text)) and count >= 2)
        return ok, f'requires_frr_{protocol}_and_two_topic_terms;matched={count}'
    return False, 'unsupported_intent'


def assess_context(bundle, intent='network_context', mode='replay', as_of=None, max_age_seconds=120):
    reasons, checks, accepted = [], [], []
    report = dict(gate_version=VERSION, intent=intent, mode=mode, decision='abstain',
                  reasons=reasons, hit_checks=checks, accepted_citations=accepted,
                  diagnosis_allowed=False, execution_allowed=False,
                  semantics='Rule-based topical context eligibility only; not semantic entailment, confidence or root cause')
    if mode not in ('replay', 'live') or not 0 < max_age_seconds <= 3600:
        reasons.append('invalid_gate_parameters')
        return report
    if intent not in SUPPORTED:
        reasons.append('unsupported_intent_or_corpus_gap')
        return report
    try:
        e = bundle['evidence']
        inputs = e['inputs']
        for entry in [inputs['graph'], inputs['snapshot'], inputs['inventory'], *inputs['logs']]:
            verify(entry['path'], entry['sha256'])
        rebuilt = context(inputs['graph']['path'], inputs['inventory']['path'], e['focus']['link'])
        if canonical_references(e) != canonical_references(rebuilt):
            raise ValueError('Bundle differs from revalidated graph/telemetry/log context')
        protocol = e['focus']['protocol']
        if e['collection_status'] != 'complete':
            reasons.append('incomplete_snapshot')
        for router in e['focus']['routers']:
            for kind in ('interfaces', protocol, 'routes'):
                rows = [r for r in e['telemetry'] if r['router'] == router and r['source'] == kind]
                if len(rows) != 1 or rows[0]['observation']['status'] != 'ok':
                    reasons.append(f'missing_or_failed_source:{router}:{kind}')
        if any(s['state'] == 'unknown' for s in e['sessions']) or e['physical'][0]['state'] == 'unknown':
            reasons.append('unknown_network_state')
        if e['physical'][0]['state'] == 'down' and not e['logs']:
            reasons.append('down_state_without_correlated_logs')
        if intent == 'bgp_session_state' and protocol != 'bgp':
            reasons.append('intent_protocol_mismatch')
        end = instant(e['window']['end'])
        now = instant(as_of) if as_of else datetime.now(timezone.utc)
        age = (now - end).total_seconds()
        report['freshness'] = dict(age_seconds=age, enforced=mode == 'live', max_age_seconds=max_age_seconds)
        if mode == 'live' and not 0 <= age <= max_age_seconds:
            reasons.append('stale_or_future_snapshot')
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        reasons.append('invalid_evidence:' + str(exc))
        return report
    for group_index, group in enumerate(bundle.get('documentation', [])):
        result = group.get('retrieval', {})
        for hit in result.get('hits', []):
            row = dict(group=group_index, id=hit.get('id'), accepted=False)
            try:
                citation(hit, result.get('platform_filter'))
                ok, rule = relevant(hit, intent, protocol)
                row.update(accepted=ok, rule=rule, provenance=True)
                if ok:
                    accepted.append(dict(id=hit['id'], citation_url=hit['metadata']['citation_url'], group=group_index))
            except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
                row.update(provenance=False, reason=str(exc))
                reasons.append('invalid_document_citation')
            checks.append(row)
    if not accepted:
        reasons.append('no_topically_relevant_verified_documentation')
    if not reasons:
        report['decision'] = 'context_ready'
    else:
        # Retain hit audit, but do not expose an approved evidence selection on abstention.
        accepted.clear()
    report['reasons'] = sorted(set(reasons))
    report['next_action'] = ('Review eligible context; diagnosis still requires reasoning and validation'
                             if report['decision'] == 'context_ready' else
                             'Collect missing/fresh evidence or retrieve verified documentation; do not generate a fix')
    return report


def assess(bundle, intent='network_context', mode='replay', as_of=None, max_age_seconds=120, question=None):
    from knowledge.question_support import check
    # Retain evidence/provenance/freshness validation, but do not use old topic
    # approval as evidence that a question is answered.
    report = assess_context(bundle, intent if intent in SUPPORTED else 'network_context', mode, as_of, max_age_seconds)
    groups = bundle.get('documentation', [])
    if question is None:
        question = bundle.get('question')
    def observation_query(group):
        q = group.get('retrieval', {}).get('query', '')
        return bool(group.get('trigger_evidence')) and (
            q.startswith('OSPF neighbor adjacency interface link state shortest path routing.') or
            q.startswith('BGP directly connected external peer interface link session reset.') or
            q == 'interface MTU maximum transmission unit admin-status oper-status' or
            q.startswith('BGP neighbor session-state '))
    questions = [question] if question else [g.get('retrieval', {}).get('query', '') for g in groups
        if not observation_query(g)]
    report['requested_intent'] = intent
    if not questions:
        if intent not in SUPPORTED:
            report['decision'] = 'abstain'
            report['reasons'].append('unsupported_intent_or_corpus_gap')
            report['accepted_citations'] = []
        report['question_support'] = []
        report['answer_supported'] = False
        report['scope'] = 'observation_context_only'
        return report
    verified = []
    for group in groups:
        for hit in group.get('retrieval', {}).get('hits', []):
            try:
                citation(hit, group['retrieval'].get('platform_filter'))
                verified.append(hit)
            except (ValueError, KeyError, TypeError, OSError, IndexError):
                pass  # Already fail-closed in provenance validation above.
    support = [check(q, verified) for q in questions]
    report['question_support'] = support
    report['scope'] = 'bounded_question_support'
    # Old topical absence is superseded by stricter claim evidence (e.g. schema).
    reasons = [r for r in report['reasons'] if r != 'no_topically_relevant_verified_documentation']
    reasons.extend(r['reason'] for r in support if not r['supported'])
    report['reasons'] = sorted(set(reasons))
    report['answer_supported'] = not reasons and bool(support)
    report['decision'] = 'context_ready' if report['answer_supported'] else 'abstain'
    report['accepted_citations'] = [c for s in support for claim in s['claims'] for c in claim['citations']] if report['answer_supported'] else []
    report['semantics'] = 'Bounded question/claim rules with verified citations; not general entailment or permission to diagnose/execute'
    report['next_action'] = 'Review cited claim evidence' if report['answer_supported'] else 'Obtain missing claim evidence or clarify unsupported question; do not invent an answer'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--intent', default='network_context')
    p.add_argument('--mode', choices=['replay', 'live'], default='replay')
    p.add_argument('--question')
    args = p.parse_args()
    source, output = local_path(args.bundle), local_path(args.output)
    if output.exists():
        raise ValueError('Choose a new output filename')
    report = assess(read(source), args.intent, args.mode, question=args.question)
    report['input_bundle'] = ref(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(decision=report['decision'], reasons=report['reasons'])))


if __name__ == '__main__':
    main()
