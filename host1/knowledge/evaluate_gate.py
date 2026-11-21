"""Development acceptance replay plus explicitly synthetic negative controls."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
from knowledge.evidence import ROOT, read, instant, ref
from knowledge.quality_gate import assess


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'data/host1/evidence-retrieval/replay-final-20261119'
    cases = []
    for link in ('L12', 'L35'):
        for phase in ('before', 'down', 'restored'):
            path = source / f'{link}-{phase}.json'
            cases.append((f'{link}-{phase}', read(path), {}, 'context_ready', ref(path), False))
    path = source / 'L35-down.json'
    base = read(path)
    origin = ref(path)
    cases.extend([
        ('bgp-state-schema', base, dict(intent='bgp_session_state'), 'context_ready', origin, False),
        ('unsupported-mtu-remediation', base, dict(intent='ospf_mtu_remediation'), 'abstain', origin, False),
        ('unsupported-question', base, dict(intent='unsupported_free_question'), 'abstain', origin, False),
        ('live-stale', base, dict(mode='live', as_of=(instant(base['evidence']['window']['end']) + timedelta(hours=1)).isoformat()), 'abstain', origin, True),
        ('live-future', base, dict(mode='live', as_of=(instant(base['evidence']['window']['end']) - timedelta(seconds=1)).isoformat()), 'abstain', origin, True),
        ('live-fresh', base, dict(mode='live', as_of=(instant(base['evidence']['window']['end']) + timedelta(seconds=30)).isoformat()), 'context_ready', origin, True),
    ])
    def altered(name, change):
        bundle = deepcopy(base)
        change(bundle)
        cases.append((name, bundle, {}, 'abstain', origin, True))
    altered('no-documents', lambda b: b.update(documentation=[]))
    altered('schema-only-not-frr-context', lambda b: b.update(documentation=[d for d in b['documentation'] if d['retrieval']['platform_filter'] == 'openconfig']))
    ospf = read(source / 'L12-down.json')
    ospf['documentation'] = deepcopy(base['documentation'])
    cases.append(('wrong-protocol-documents', ospf, {}, 'abstain', ref(source / 'L12-down.json'), True))
    mtu = deepcopy(base)
    mtu_result = read(ROOT / 'data/host1/retriever/evaluation-hybrid-20261119/oc-mtu.json')
    mtu['documentation'] = [dict(retrieval=mtu_result)]
    cases.append(('mtu-definition-only', mtu, dict(intent='interface_mtu_definition'), 'context_ready', origin, True))
    altered('changed-snapshot-hash', lambda b: b['evidence']['inputs']['snapshot'].update(sha256='bad'))
    altered('missing-telemetry', lambda b: b['evidence'].update(telemetry=[]))
    altered('missing-logs', lambda b: b['evidence'].update(logs=[]))
    altered('forged-quotation', lambda b: b['documentation'][0]['retrieval']['hits'][0].update(text='fake BGP neighbor session'))
    altered('wrong-platform', lambda b: b['documentation'][0]['retrieval'].update(platform_filter='openconfig'))
    altered('forged-url', lambda b: b['documentation'][0]['retrieval']['hits'][0]['metadata'].update(citation_url='https://example.invalid/fake'))
    altered('conflicting-physical-state', lambda b: b['evidence']['physical'][0].update(state='up'))
    rows = []
    for name, bundle, options, expected, origin, synthetic in cases:
        result = assess(bundle, **options)
        passed = result['decision'] == expected and not result['execution_allowed'] and not result['diagnosis_allowed']
        if expected == 'abstain':
            passed = passed and bool(result['reasons']) and not result['accepted_citations']
        artifact = dict(input_bundle=origin, synthetic_control=synthetic, options=options,
                        expected=expected, passed=passed, result=result)
        (output / (name + '.json')).write_text(json.dumps(artifact, indent=2) + '\n', encoding='utf-8')
        rows.append(dict(case=name, expected=expected, actual=result['decision'], passed=passed,
                         reasons=result['reasons'], accepted=len(result['accepted_citations']), synthetic=synthetic))
        print(json.dumps(rows[-1]), flush=True)
    summary = dict(passed=all(r['passed'] for r in rows), cases=len(rows), rows=rows,
                   scope='Development acceptance and synthetic controls, not held-out relevance accuracy')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1])))
