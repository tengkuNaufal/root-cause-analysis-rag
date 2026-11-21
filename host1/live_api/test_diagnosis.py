"""Explicit live labels stay independent of proposal targets and replay v1."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from pydantic import ValidationError
from agent_contract.models import Response as ReplayResponse
from .examples import examples
from .models import WireResponse, Job, validate_live_pair


def agent_input(job):
    return dict(schema_version=1,request_id=job['request_id'],lab='rca',question='Synthetic test',mode='live',
                snapshot_completed_at=job['updated_at'],execution_allowed=False,
                gate=dict(version='test',decision='context_ready',answer_supported=True,reasons=[]),
                evidence=[dict(id='e1',kind='telemetry',source_path='synthetic',sha256='0'*64,locator='/',content='Synthetic only')])

class DiagnosisTests(unittest.TestCase):
    def test_labels_required_and_strict_vocabulary(self):
        result=examples()['hypothesis']['result']
        for key,value in [('root_cause_class','not_a_class'),('root_cause_router','r7'),
                          ('root_cause_class',None)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValidationError):
                WireResponse.model_validate({**result,key:value})
        for key in ('root_cause_class','root_cause_router'):
            changed={k:v for k,v in result.items() if k!=key}
            with self.assertRaises(ValidationError):WireResponse.model_validate(changed)

    def test_abstain_requires_both_labels_null(self):
        result=examples()['abstain']['result']
        self.assertIsNone(WireResponse.model_validate(result).root_cause_class)
        for key,value in [('root_cause_class','unknown'),('root_cause_router','r1')]:
            with self.assertRaises(ValidationError):WireResponse.model_validate({**result,key:value})

    def test_empty_patch_preserves_diagnosis_and_other_router_is_allowed(self):
        job=examples()['hypothesis']
        job['result']['root_cause_router']='r2';job['assessment']['router']='r2'
        validated=Job.model_validate(job).root
        self.assertEqual(validated.result.proposed_patch[0].router,'r1')
        self.assertEqual(validated.result.root_cause_router,'r2')
        job['result']['proposed_patch']=[];job['assessment']['commands']=[]
        validated=Job.model_validate(job).root
        self.assertEqual(validated.assessment.router,'r2')
        self.assertEqual(validated.result.root_cause_class,'mtu_mismatch')

    def test_assessment_must_match_labels_and_unknown_mapping(self):
        for key,value in [('router','r2'),('root_cause','link_down')]:
            job=examples()['hypothesis'];job['assessment'][key]=value
            with self.assertRaises(ValidationError):Job.model_validate(job)
        job=examples()['hypothesis']
        job['result'].update(root_cause_class='unknown',root_cause_router=None)
        job['assessment'].update(root_cause='unknown',router=None)
        Job.model_validate(job)
        abstain=Job.model_validate(examples()['abstain']).root
        self.assertEqual(abstain.assessment.root_cause,'unknown')
        self.assertIsNone(abstain.result.root_cause_class)

    def test_live_pair_keeps_gate_and_reference_guards(self):
        job=examples()['hypothesis'];req=agent_input(job);result=job['result']
        validate_live_pair(req,result)
        for edit in [lambda r:r.update(mode='replay'),
                     lambda r:r.update(request_id='different'),
                     lambda r:r['gate'].update(decision='abstain',answer_supported=False),
                     lambda r:r['evidence'][0].update(id='other')]:
            changed=deepcopy(req);edit(changed)
            with self.assertRaises(ValueError):validate_live_pair(changed,result)

    def test_replay_v1_does_not_accept_live_extensions(self):
        result=examples()['hypothesis']['result']
        with self.assertRaises(ValidationError):ReplayResponse.model_validate(result)
        old={k:v for k,v in result.items() if k not in ('root_cause_class','root_cause_router')}
        ReplayResponse.model_validate(old)

    def test_live_schema_contains_all_catalog_classes_without_loading_cases_into_agent(self):
        import yaml
        root=Path(__file__).resolve().parents[2]
        catalog=yaml.safe_load((root/'faults/host1.yaml').read_text())
        classes={f['class'] for f in catalog['faults']}|{'unknown'}
        field=WireResponse.model_json_schema()['properties']['root_cause_class']
        self.assertEqual(set(field['anyOf'][0]['enum']),classes)

    def test_existing_linter_accepts_live_result_and_wire_commands(self):
        from rca.linter import lint
        job=examples()['hypothesis']
        self.assertTrue(lint(job['result'])['passed'])
        self.assertTrue(lint(job['assessment']['commands'])['passed'])
        job['result']['root_cause_router']='r2'
        self.assertTrue(lint(job['result'])['passed'])

if __name__=='__main__':unittest.main()
