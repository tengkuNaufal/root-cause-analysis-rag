"""Temporal evidence visibility, ordering, and fail-closed validation checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from knowledge.evidence import ROOT, read
from reasoning_agent.rca_gate import mechanism
from reasoning_agent.temporal import view, supported_outcome, validate_prediction, run, validate_observations, expected_observations, frame, token_budget, SYSTEM, OBSERVATION_SYSTEM, PhaseDraft

BASE=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'

class TemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles={l+'-'+s:read(BASE/(l+'-'+s+'.json')) for l in ('L12','L35') for s in ('before','down','restored')}
        cls.docs={p:mechanism(p) for p in ('ospf','bgp')}

    def selected(self,name='L12-restored',**options):
        b=deepcopy(self.bundles[name]);gate=dict(mechanism=self.docs[b['evidence']['focus']['protocol']],
            gate_version='test',decision='context_ready',answer_supported=True,reasons=[])
        req,payload,prompt,allowance=view(b,gate,'t-test',options=options)
        return b,req,payload,prompt,allowance

    def response(self,req,payload,e):
        expected=supported_outcome(e,payload)
        ids=[r.id for r in req.evidence if r.kind!='documentation']
        return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=100,
                    response=json.dumps(dict(**expected,explanation='Synthetic model test reply.',citations=ids)))

    def test_normal_and_transformed_views_fit(self):
        for name in self.bundles:
            for options in ({},{'reverse_endpoints':True,'opaque_ids':True},{'reverse_events':True,'doc_last':True}):
                b,req,payload,prompt,a=self.selected(name,**options)
                self.assertLessEqual(a['prompt_upper_bound']+256+64,2048)
                self.assertNotIn('/restored/',prompt);self.assertNotIn('/down/',prompt)

    def test_endpoint_reversal_preserves_evidence_values(self):
        b,req,payload,prompt,a=self.selected('L12-down',reverse_endpoints=True,opaque_ids=True)
        self.assertEqual(payload['current']['interfaces'][1]['node'],'r1:eth1')
        self.assertIs(payload['current']['interfaces'][1]['admin_up'],False)
        self.assertEqual(supported_outcome(b['evidence'],payload)['target'],'r1:eth1')

    def test_reversed_history_is_chronologically_classified(self):
        b,req,payload,prompt,a=self.selected(reverse_events=True)
        self.assertEqual(payload['history']['events'][0]['event'],'UP')
        self.assertEqual(supported_outcome(b['evidence'],payload)['phase'],'recovered')

    def test_down_only_history_is_not_current_fault(self):
        b,req,payload,prompt,a=self.selected(history='down_only')
        self.assertFalse(payload['history']['complete'])
        self.assertEqual(supported_outcome(b['evidence'],payload),dict(current='healthy',phase='undetermined',target=None))

    def test_hidden_history_cannot_prove_recovery(self):
        b,req,payload,prompt,a=self.selected(history='none')
        self.assertEqual(payload['history']['events'],[])
        self.assertFalse(any(r.kind=='log' for r in req.evidence))
        self.assertEqual(supported_outcome(b['evidence'],payload)['phase'],'undetermined')

    def test_valid_cited_prediction_maps_to_official_contract(self):
        b,req,payload,prompt,a=self.selected()
        draft,result=validate_prediction(req,self.response(req,payload,b['evidence']),a,b['evidence'],payload)
        self.assertEqual(draft.phase,'recovered');self.assertIs(result['execution_allowed'],False)
        self.assertEqual(result['proposed_patch'],[])

    def test_missing_temporal_citation_rejected(self):
        self.reject(lambda p:p.update(citations=['T1','T2','G1']))

    def test_wrong_phase_rejected_without_replacing_prediction(self):
        self.reject(lambda p:p.update(phase='baseline'))

    def test_unknown_citation_rejected(self):
        self.reject(lambda p:p.update(citations=['invented']))

    def test_execution_extra_field_rejected(self):
        self.reject(lambda p:p.update(execution_allowed=True))

    def reject(self,change):
        b,req,payload,prompt,a=self.selected();raw=self.response(req,payload,b['evidence'])
        value=json.loads(raw['response']);change(value);raw['response']=json.dumps(value)
        with self.assertRaises(ValueError):validate_prediction(req,raw,a,b['evidence'],payload)

    def test_truncation_rejected(self):
        b,req,payload,prompt,a=self.selected();raw=self.response(req,payload,b['evidence']);raw['done_reason']='length'
        with self.assertRaises(ValueError):validate_prediction(req,raw,a,b['evidence'],payload)

    def test_healthy_case_still_calls_model_and_does_not_correct_bad_answer(self):
        class WrongModel:
            called=False
            def generate(self,request):
                self.called=True
                if request['format'].get('title')=='ObservationDraft':
                    return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=100,response=json.dumps(
                        dict(admin_down=[],carrier_down=[],peer_states=['Full/-','Full/-'],physical='up',history_complete=True,events_time_order=[])))
                return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=100,
                    response=json.dumps(dict(phase='fault')))
        with tempfile.TemporaryDirectory(dir=ROOT/'data/host1') as tmp:
            model=WrongModel();audit=run(BASE/'L12-before.json',Path(tmp)/'out',transport=model,extractor='grouped')
            self.assertTrue(model.called);self.assertTrue(audit['model_called'])
            self.assertEqual(audit['raw_prediction']['phase'],'fault');self.assertEqual(audit['status'],'abstain')

    def test_fact_extraction_is_checked_not_repaired(self):
        b,req,payload,prompt,a=self.selected('L35-down')
        facts=expected_observations(payload);facts['admin_down']=[]
        with self.assertRaisesRegex(ValueError,'fact_extraction_conflicts'):
            validate_observations(facts,payload)

    def test_two_stage_prompts_fit_each_context(self):
        for name in self.bundles:
            b,req,payload,prompt,a=self.selected(name)
            facts=expected_observations(payload)
            for text in (frame(OBSERVATION_SYSTEM,dict(current=payload['current'],history=payload['history'])),
                         frame(SYSTEM,dict(model_observations=facts))):
                self.assertLessEqual(token_budget(text)['prompt_upper_bound']+256+64,2048)

    def test_phase_wire_rejects_invented_actor_prose(self):
        with self.assertRaises(ValueError):
            PhaseDraft.model_validate(dict(phase='fault',explanation='Manual intervention'))

    def test_evaluator_maps_state_to_current_without_hiding_target_errors(self):
        from reasoning_agent.evaluate_temporal import score_prediction
        raw=dict(current='healthy',phase='baseline',target='r1:eth1',explanation='Synthetic.',citations=['T1'])
        score=score_prediction(raw,dict(state='healthy',phase='baseline',target=None))
        self.assertTrue(score['raw_state_phase_correct']);self.assertFalse(score['raw_classification_correct'])
        self.assertFalse(score['draft_valid'])
        raw['target']=None;score=score_prediction(raw,dict(state='healthy',phase='baseline',target=None))
        self.assertTrue(score['raw_classification_correct']);self.assertTrue(score['draft_valid'])

if __name__=='__main__':unittest.main()
