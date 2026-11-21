"""Bounded, source-checked explanation reports for saved temporal runs; no inference/executor."""
from copy import deepcopy
import json
from agent_contract.models import Request, validate_pair
from knowledge.evidence import canonical_references, read, local_path, verify, ref
from reasoning_agent.rca_gate import assess_rca
from reasoning_agent.temporal import (view, validate_prediction, token_budget, validate_observations,
    PhaseDraft, combine_model_outputs)

BOUNDARY=('Kondisi administratif DOWN adalah kondisi lokal terdekat yang didukung observasi; '
          'pelaku, perintah pemicu, kerusakan kabel/perangkat, dan penyebab awal belum terbukti. '
          'Snapshot tidak atomik; korelasi waktu bukan pembuktian kausalitas umum.')
HEALTHY_BOUNDARY=('Kesimpulan hanya berlaku pada link fokus dan window yang diberikan, bukan seluruh jaringan '
                  'atau bukti bahwa gangguan tidak pernah terjadi. Penyebab awal gangguan tidak ditetapkan.')

def load_run(directory):
    directory=local_path(directory);audit=read(directory/'audit.json')
    source=verify(audit['bundle']['path'],audit['bundle']['sha256']);bundle=read(source)
    gate=assess_rca(bundle,audit['mode'])
    if not gate['hypothesis_allowed']:raise ValueError('explanation_source_gate_abstain')
    req=Request.model_validate(read(directory/'input-contract.json'))
    rebuilt,payload,_,_=view(bundle,gate,req.request_id,audit['mode'],audit['options'])
    if (canonical_references(rebuilt.model_dump()) != canonical_references(req.model_dump())
            or payload != read(directory/'visible-evidence.json')):
        raise ValueError('saved_selection_differs_from_sources')
    raw=read(directory/'ollama-response.json');prediction=read(directory/'combined-model-prediction.json')
    phase=json.loads(raw['response'])
    if phase!=read(directory/'raw-phase.json') or phase.get('phase')!=prediction['phase']:
        raise ValueError('phase_provenance_mismatch')
    observations=validate_observations(read(directory/'raw-observations.json'),payload)
    if prediction!=combine_model_outputs(observations,PhaseDraft.model_validate(phase),payload):
        raise ValueError('saved_prediction_differs_from_model_values_and_renderer')
    prompt=(directory/'prompt.txt').read_text();allowance=token_budget(prompt)
    draft,expected=validate_prediction(req,dict(raw,response=json.dumps(prediction)),allowance,bundle['evidence'],payload)
    result=read(directory/'output-contract.json');validate_pair(req.model_dump(),result)
    if result!=expected or not audit.get('contract_valid'):raise ValueError('saved_contract_mismatch')
    return directory,bundle,req,payload,prediction,result,audit

def claim(key,role,statement,citations,**values):
    return dict(key=key,role=role,statement=statement,citations=citations,values=values)

def supported_claims(req,payload,prediction):
    """Exact finite claims; not an entailment checker for arbitrary prose."""
    claims=[]
    for row in payload['current']['interfaces']:
        node=row['node'];admin='UP' if row['admin_up'] else 'DOWN';carrier='UP' if row['carrier_up'] else 'DOWN'
        claims.append(claim('interface:'+node,'observed_condition' if not row['admin_up'] else 'observation',
            f'{node}: admin {admin}, carrier {carrier} pada snapshot link fokus.',[row['ref']],
            node=node,admin_up=row['admin_up'],carrier_up=row['carrier_up']))
    g=payload['current']['graph'];graph=json.loads(next(r.content for r in req.evidence if r.id==g['ref']))
    claims.append(claim('physical','symptom','Graf link fokus menunjukkan physical='+g['physical']+'.',
                        [g['ref']],physical=g['physical']))
    for s in graph['sessions']:
        node=s['source'].split(':',1)[1]
        claims.append(claim('peer:'+node,'symptom',f'Observasi peer {node}: state={s["state"]}.',
                            [g['ref']],router=node,state=s['state']))
    for event in payload['history']['events']:
        claims.append(claim('event:'+event['ref'],'historical_observation',
            f'Log peer/interface terkait mencatat {event["event"]} pada {event["time"]}; ini peristiwa historis.',
            [event['ref']],event=event['event'],time=event['time']))
    phase=prediction['phase'];texts=dict(
        fault='Fase fault: kondisi administratif DOWN teramati bersama kehilangan carrier/protokol.',
        baseline='State saat ini sehat; tidak ada transisi DOWN/UP dalam history yang dinyatakan lengkap pada view ini.',
        recovered='State saat ini sehat; history view mencatat DOWN kemudian UP menurut timestamp.',
        undetermined='State saat ini sehat; history parsial tidak cukup membedakan baseline dari pemulihan.')
    ids=list(payload['required_current_refs'])+['V1']
    if phase=='recovered':ids += [x['ref'] for x in payload['history']['events']]
    claims.append(claim('phase','bounded_interpretation',texts[phase],ids,phase=phase,
                        history_complete=payload['history']['complete']))
    if phase=='fault':
        target=prediction['target'];row=next(r for r in payload['current']['interfaces'] if r['node']==target)
        claims.append(claim('nearest_condition','observed_contributing_condition',
            f'Kondisi lokal terdekat yang terbukti pada observasi: {target} administratif DOWN. '
            'Hal ini tidak menetapkan penyebab awal atau pelakunya.',[row['ref']],node=target,admin_up=False))
        doc=next(r for r in req.evidence if r.kind=='documentation')
        protocol=payload['current']['protocol']
        mechanism='InterfaceDown/KillNbr OSPF' if protocol=='ospf' else 'fast-external-failover BGP'
        claims.append(claim('mechanism','documented_mechanism',
            f'Dokumentasi menjelaskan mekanisme {mechanism}; dokumentasi bukan bukti konfigurasi aktif atau penyebab kejadian.',
            [doc.id],protocol=protocol))
    return claims

def build(req,payload,prediction,directory):
    citations=[r.model_dump() for r in req.evidence]
    if any(r['id']=='V1' for r in citations):raise ValueError('reserved_view_citation_collision')
    citations.append(dict(id='V1',kind='audit_view',source_path=ref(directory/'visible-evidence.json')['path'],
        sha256=ref(directory/'visible-evidence.json')['sha256'],locator='/history',
        content=json.dumps(payload['history']),semantics='Visibility/coverage of supplied view, not a new telemetry observation'))
    return dict(schema_version='bounded-explanation-1.0',explanation_origin='controller_rendered_validated_claims',
        phase_origin='saved_llm_response',scope='focus_link_snapshot_and_supplied_history_only',
        root_cause_status='not_established',claims=supported_claims(req,payload,prediction),citations=citations,
        limitations=BOUNDARY if prediction['phase']=='fault' else HEALTHY_BOUNDARY,
        diagnosis_allowed=False,execution_allowed=False,proposed_patch=[])

def validate_report(report,req,payload,prediction,directory):
    # Equality checks every value, role, text and exact supporting citation set.
    # Unknown free text cannot acquire approval by attaching a valid ID.
    if report!=build(req,payload,prediction,directory):
        raise ValueError('unsupported_or_misattributed_explanation_claim')
    return deepcopy(report)

def render(report):
    lines=[f'Fase: {next(c for c in report["claims"] if c["key"]=="phase")["values"]["phase"]}',
           'Asal penjelasan: controller; fase: hasil LLM tersimpan.','']
    lines += ['- '+c['statement']+' ['+', '.join(c['citations'])+']' for c in report['claims']]
    lines += ['', 'Batas kesimpulan: '+report['limitations'],'', 'Penelusuran citation:']
    lines += ['- '+c['id']+': '+c['source_path']+'; '+c['locator']+'; sha256='+c['sha256'] for c in report['citations']]
    return '\n'.join(lines)+'\n'
