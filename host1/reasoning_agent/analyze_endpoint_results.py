"""Summarize paired cells and audit actual source bindings and request invariance."""
import hashlib
import json
import sys
from knowledge.evidence import local_path, read, verify
from reasoning_agent.evaluate_endpoints import fingerprints
from reasoning_agent.temporal import validate_endpoint
from reasoning_agent.rca_gate import assess_rca

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main(directory):
    directory=local_path(directory);registered=read(directory/'preregistered.json')
    for name,sha in registered['hashes'].items():verify(directory/name,sha)
    manifest=read(directory/'factorial.json');controls=read(directory/'controls.json')
    lookup={x['id']:x for x in manifest+controls}
    reports={label:read(directory/label/'summary.json') for label in ('factorial-grouped','factorial-bound','controls-bound')}
    freezes={label:read(directory/label/'implementation-freeze.json') for label in reports}
    current=fingerprints()
    if any(f['code']!=current for f in freezes.values()):raise ValueError('Frozen implementation changed')
    source_checks={}
    for case in manifest+controls:
        path=verify(case['bundle'],case['sha256'])
        if str(path) not in source_checks:
            gate=assess_rca(read(path))
            if not gate['hypothesis_allowed']:raise ValueError('Source gate no longer ready')
            source_checks[str(path)]=True
    rows=[]
    indexed={label:{r['id']:r for r in report['cases']} for label,report in reports.items()}
    for order in ('normal','reversed'):
        for citation in ('native','fresh'):
            ids=[c['id'] for c in manifest if c['factors']==dict(order=order,citation=citation)]
            rows.append(dict(order=order,citation=citation,total=len(ids),
                grouped_accepted=sum(indexed['factorial-grouped'][i]['contract_accepted'] for i in ids),
                bound_accepted=sum(indexed['factorial-bound'][i]['contract_accepted'] for i in ids)))
    request_hashes={};binding_checks=[]
    for label in ('factorial-bound','controls-bound'):
        for item in reports[label]['cases']:
            path=directory/label/item['id'];payload=read(path/'visible-evidence.json')
            source_rows={r['node']:r for r in payload['current']['interfaces']}
            if not item['contract_accepted']:
                binding_checks.append(dict(case=item['id'],complete=False));continue
            records=read(path/'endpoint-bindings.json');node_requests={}
            if {r['node'] for r in records}!=set(source_rows):raise ValueError('Endpoint set differs')
            for index,record in enumerate(records,1):
                source=source_rows[record['node']]
                if record['citation']!=source['ref']:raise ValueError('Citation bound to wrong endpoint')
                values=read(path/f'endpoint-{index}-raw.json')
                if values!=record['model_values']:raise ValueError('Saved model values differ from raw response')
                validate_endpoint(values,source)
                if read(path/f'endpoint-{index}-binding.json')!=dict(node=source['node'],citation=source['ref']):
                    raise ValueError('Pre-inference binding differs')
                node_requests[record['node']]=digest(read(path/f'endpoint-{index}-request.json'))
            request_hashes[item['id']]=dict(endpoints=node_requests,
                context=digest(read(path/'history-context-request.json')),phase=digest(read(path/'ollama-request.json')))
            binding_checks.append(dict(case=item['id'],complete=True))
    invariance=[]
    for link in ('L12','L35'):
        cases=[c for c in manifest if c['link']==link]
        records=[request_hashes.get(c['id']) for c in cases]
        complete=all(r is not None for r in records)
        invariance.append(dict(link=link,complete=complete,
            all_endpoint_requests_equal=complete and all(r['endpoints']==records[0]['endpoints'] for r in records),
            all_context_requests_equal=complete and all(r['context']==records[0]['context'] for r in records),
            all_phase_requests_equal=complete and all(r['phase']==records[0]['phase'] for r in records)))
    result=dict(code_unchanged=True,data_unchanged=True,cells=rows,
        summaries={label:{key:value for key,value in report.items() if key!='cases'} for label,report in reports.items()},
        binding_checks=binding_checks,request_invariance=invariance,
        interpretation='Bound removes citation IDs from model inputs and binds identity in controller; do not claim learned ID/permutation robustness.',
        scope='Single run per factorial cell on two stored traces, not independent fault accuracy')
    target=directory/'paired-analysis.json'
    if target.exists():raise ValueError('Analysis exists; preserve original evidence')
    target.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main(sys.argv[1])
