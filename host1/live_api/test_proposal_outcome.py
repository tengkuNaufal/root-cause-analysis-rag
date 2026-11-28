"""Diagnosis survives known proposal policy rejection; integrity failures remain fatal."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .agent import DiagnosisEngine, DiagnosisError
from .capture import write
from .models import Job
from .test_agent import FixtureCapture, run_engine
from .test_pilot_agent import cases
from scripts.proposal_outcome import read_rejection


def proposal_engine(cause, args, tool='vtysh', *, model_cause=None):
    facts=next(c[1] for c in cases() if c[0]==cause)
    class Capture(FixtureCapture):
        def capture(self,directory):
            data=super().capture(directory)
            data['facts']['observations']=deepcopy(facts)
            data['metadata']['facts_sha256']=write(directory/'facts.json',data['facts'])
            return data
    class Model:
        def generate(self,payload):
            value=dict(root_cause_class=model_cause or cause,root_cause_router='r1',confidence=.8,
                explanation='Synthetic observed deviation.',evidence_ids=['e1'],
                commands=[dict(router='r1',interpreter=tool,args=args)])
            if payload['format'].get('type')=='array':
                value=[value['root_cause_class'],'r1',.8,value['explanation'],['e1'],[['r1',tool,args]]]
            return dict(done=True,done_reason='stop',prompt_eval_count=10,eval_count=20,response=json.dumps(value))
    return DiagnosisEngine(capture=Capture(),model=Model())


class ProposalOutcomeTests(unittest.TestCase):
    def test_linter_and_semantic_rejections_preserve_exact_diagnosis_with_empty_patch(self):
        for cause,args,stage,code in [
            ('ospf_hello_mismatch',['configure terminal','interface eth1','ospf hello-interval 1'],
             'lint','proposed_patch_rejected_by_linter'),
            ('ospf_area_mismatch',['configure terminal','interface eth1','ip ospf area 0'],
             'guard','proposal_does_not_restore_observed_baseline')]:
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as tmp:
                job=run_engine(proposal_engine(cause,args),tmp);Job.model_validate(job)
                outcome=read_rejection(job)
                self.assertEqual((outcome['stage'],outcome['code']),(stage,code))
                self.assertEqual(job['state'],'completed');self.assertEqual(job['result']['status'],'hypothesis')
                self.assertEqual(job['assessment']['root_cause'],cause);self.assertEqual(job['assessment']['router'],'r1')
                self.assertEqual(job['assessment']['confidence'],.8)
                self.assertEqual(job['assessment']['evidence_ids'],['e1'])
                self.assertEqual(job['assessment']['explanation'],'Synthetic observed deviation.')
                self.assertEqual(job['assessment']['commands'],[]);self.assertEqual(job['result']['proposed_patch'],[])
                self.assertFalse(job['execution_allowed'])
                directory=next(Path(tmp).iterdir())
                audit=json.loads((directory/'proposal-validation.json').read_text())
                self.assertTrue(audit['candidate']['proposed_patch'])
                self.assertEqual(len(outcome['commands_sha256']),64)
                self.assertEqual(outcome['candidate_count'],1)

    def test_wrong_diagnosis_is_not_salvaged_as_completed(self):
        eng=proposal_engine('bgp_wrong_remote_as',['configure terminal','router bgp 65001',
                            'no neighbor 10.255.0.2 shutdown'],model_cause='bgp_neighbor_shutdown')
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(DiagnosisError,'not_supported'):
            run_engine(eng,tmp)

    def test_unknown_evidence_reference_remains_fatal(self):
        eng=proposal_engine('ospf_area_mismatch',['configure terminal','interface eth1','ip ospf area 0'])
        original=eng.model.generate
        def generate(payload):
            result=original(payload);value=json.loads(result['response']);value['evidence_ids']=['e999']
            result['response']=json.dumps(value);return result
        eng.model.generate=generate
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'Unknown evidence reference'):
            run_engine(eng,tmp)

    def test_unexpected_validator_error_remains_fatal(self):
        eng=proposal_engine('ospf_area_mismatch',['configure terminal','interface eth1','ip ospf area 0'])
        with tempfile.TemporaryDirectory() as tmp,patch('rca.linter.lint',side_effect=RuntimeError('synthetic bug')):
            with self.assertRaises(RuntimeError):run_engine(eng,tmp)

    def test_source_hash_failure_is_not_hidden_by_proposal_rejection(self):
        eng=proposal_engine('ospf_area_mismatch',['configure terminal','interface eth1','ip ospf area 0'])
        original=eng._verify_sources;calls=[]
        def verify(directory,refs):
            calls.append(1)
            if len(calls)>1:raise DiagnosisError('evidence_changed')
            return original(directory,refs)
        eng._verify_sources=verify
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(DiagnosisError,'evidence_changed'):
            run_engine(eng,tmp)

    def test_exported_rejection_note_cannot_accompany_commands_or_abstain(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=run_engine(proposal_engine('ospf_area_mismatch',
                ['configure terminal','interface eth1','ip ospf area 0']),tmp)
        for mutate in [lambda j:j['assessment'].update(commands=[{}]),lambda j:j['result'].update(status='abstain'),
                       lambda j:j['result']['missing_evidence'].append(j['result']['missing_evidence'][0])]:
            changed=deepcopy(job);mutate(changed)
            with self.assertRaises(ValueError):read_rejection(changed)
