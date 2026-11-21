"""RCA state/temporal/target checks; synthetic edits do not mutate source evidence."""
from copy import deepcopy
import json
import unittest
from knowledge.evidence import ROOT, read
from reasoning_agent.rca_gate import assess_rca, state_scope, scoped_events, mechanism
from reasoning_agent.rca import select, validate_draft, observed_healthy

BASE=ROOT/'data/host1/evidence-retrieval/replay-final-20261119'

class RcaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles={link+'-'+phase:read(BASE/(link+'-'+phase+'.json'))
                     for link in ('L12','L35') for phase in ('before','down','restored')}
        cls.docs={p:mechanism(p) for p in ('ospf','bgp')}

    def bundle(self,name='L12-down'):return deepcopy(self.bundles[name])

    def selected(self,name='L12-down'):
        b=self.bundle(name);d=self.docs[b['evidence']['focus']['protocol']]
        gate=dict(mechanism=d,gate_version='link-rca-1.0',decision='context_ready',answer_supported=True,reasons=[])
        req,prompt,allowance,view=select(b,gate,'r-test','replay')
        return b,req,allowance

    def raw(self,assessment='active_admin_down',target='r1:eth1',ids=None):
        return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=100,
            response=json.dumps(dict(assessment=assessment,hypothesis='Synthetic test statement; not real model output.',
                target=target,evidence_ids=ids or ['D1','T1','T2','G1','L1'],missing_evidence=[])))

    def test_all_six_state_scopes(self):
        for name,b in self.bundles.items():
            self.assertEqual(state_scope(b['evidence']), 'coherent_admin_down_context' if name.endswith('-down') else 'coherent_up_context')

    def test_all_six_prompts_fit_context(self):
        for name in self.bundles:
            b,req,a=self.selected(name)
            self.assertLessEqual(a['prompt_upper_bound']+512+64,2048)

    def test_directed_peer_specific_down_logs(self):
        for link in ('L12','L35'):
            e=self.bundle(link+'-down')['evidence'];events=scoped_events(e)
            self.assertEqual({x['row']['event']['router'] for x in events if x['transition']=='down'},set(e['focus']['routers']))

    def test_recovered_context_retains_down_and_up_history(self):
        for link in ('L12','L35'):
            self.assertEqual({x['transition'] for x in scoped_events(self.bundle(link+'-restored')['evidence'])},{'down','up'})

    def test_wrong_peer_log_not_selected(self):
        e=self.bundle()['evidence']
        for row in e['logs']: row['event']['message']=row['event']['message'].replace('10.0.12.','192.0.2.')
        self.assertEqual(scoped_events(e),[])

    def test_cable_only_state_abstains(self):
        e=self.bundle()['evidence'];e['interfaces'][0]['observed']['admin_up']=True
        with self.assertRaises(ValueError):state_scope(e)

    def test_mtu_mismatch_outside_profile(self):
        e=self.bundle()['evidence'];e['interfaces'][0]['observed']['mtu']=1400
        with self.assertRaisesRegex(ValueError,'mtu_mismatch'):state_scope(e)

    def test_unknown_interface_state_abstains(self):
        e=self.bundle()['evidence'];e['interfaces'][0]['observed']['admin_up']=None
        with self.assertRaises(ValueError):state_scope(e)

    def test_tampered_snapshot_hash_rejected(self):
        b=self.bundle();b['evidence']['inputs']['snapshot']['sha256']='0'*64
        self.assertFalse(assess_rca(b)['hypothesis_allowed'])

    def test_stale_live_evidence_rejected(self):
        self.assertFalse(assess_rca(self.bundle(),mode='live',as_of='2099-01-01T00:00:00Z')['hypothesis_allowed'])

    def test_wrong_admin_target_rejected(self):
        b,req,a=self.selected()
        with self.assertRaisesRegex(ValueError,'wrong_admin_down_target'):
            validate_draft(req,self.raw(target='r2:eth1'),a,b['evidence'])

    def test_old_down_log_cannot_override_recovery(self):
        b,req,a=self.selected('L12-restored')
        with self.assertRaisesRegex(ValueError,'historical_log'):
            validate_draft(req,self.raw(),a,b['evidence'])

    def test_down_cannot_be_reported_healthy(self):
        b,req,a=self.selected()
        with self.assertRaises(ValueError):validate_draft(req,self.raw('no_current_fault',None),a,b['evidence'])

    def test_missing_cross_source_citations_rejected(self):
        b,req,a=self.selected()
        with self.assertRaises(ValueError):validate_draft(req,self.raw(ids=['D1']),a,b['evidence'])

    def test_unknown_reference_rejected(self):
        b,req,a=self.selected()
        with self.assertRaises(ValueError):validate_draft(req,self.raw(ids=['D1','T1','T2','G1','invented']),a,b['evidence'])

    def test_truncated_output_rejected(self):
        b,req,a=self.selected();raw=self.raw();raw['done_reason']='length'
        with self.assertRaises(ValueError):validate_draft(req,raw,a,b['evidence'])

    def test_execution_field_cannot_be_added(self):
        b,req,a=self.selected();raw=self.raw();draft=json.loads(raw['response']);draft['execution_allowed']=True
        raw['response']=json.dumps(draft)
        with self.assertRaises(ValueError):validate_draft(req,raw,a,b['evidence'])

    def test_assessment_labels_are_not_missing_evidence(self):
        b,req,a=self.selected();raw=self.raw();draft=json.loads(raw['response'])
        draft['missing_evidence']=['no_current_fault'];raw['response']=json.dumps(draft)
        with self.assertRaisesRegex(ValueError,'assessment_labels_are_not_missing_evidence'):
            validate_draft(req,raw,a,b['evidence'])

    def test_supported_structured_hypothesis_validates_contract(self):
        b,req,a=self.selected();draft,response=validate_draft(req,self.raw(),a,b['evidence'])
        self.assertEqual(draft.target,'r1:eth1');self.assertEqual(response['proposed_patch'],[])
        self.assertIs(response['execution_allowed'],False)

    def test_rule_reports_healthy_only_from_current_states(self):
        for name in ('L12-before','L12-restored','L35-before','L35-restored'):
            b,req,a=self.selected(name);result=observed_healthy(req,b['evidence'])
            self.assertIn('No current fault',result['root_cause_hypothesis'])
            self.assertEqual(result['claims'][0]['evidence_ids'],['T1','T2','G1'])

    def test_healthy_rule_cannot_hide_observed_failure(self):
        b,req,a=self.selected()
        with self.assertRaises(ValueError):observed_healthy(req,b['evidence'])

    def test_unbounded_or_duplicate_output_lists_rejected(self):
        b,req,a=self.selected();raw=self.raw();draft=json.loads(raw['response'])
        draft['missing_evidence']=['invented']*3;raw['response']=json.dumps(draft)
        with self.assertRaises(ValueError):validate_draft(req,raw,a,b['evidence'])
        draft['missing_evidence']=[];draft['evidence_ids']=['D1','T1','T2','G1','L1','L1']
        raw['response']=json.dumps(draft)
        with self.assertRaisesRegex(ValueError,'duplicate_evidence_ids'):validate_draft(req,raw,a,b['evidence'])

    def test_controller_explanation_preserves_original_and_marks_origin(self):
        from reasoning_agent.report_rca import explain
        b,req,a=self.selected();draft,result=validate_draft(req,self.raw(),a,b['evidence'])
        audit=dict(assessment=draft.assessment,target=draft.target,analysis_origin='ollama_hypothesis',model_called=True)
        report=explain(b,req,audit,result,{})
        self.assertEqual(report['original_contract_hypothesis'],result['root_cause_hypothesis'])
        self.assertIn('administratively DOWN',report['explanation'])
        self.assertEqual(len(report['causal_chain']),4)
        self.assertIs(report['execution_allowed'],False)

if __name__=='__main__':unittest.main()
