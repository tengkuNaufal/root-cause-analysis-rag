"""MTU profile boundaries, citations and model rejection; no real model in unit tests."""
from copy import deepcopy
import json
import unittest
import uuid
from knowledge.evidence import ROOT, read, local_path
from reasoning_agent.mtu import prepare_input, expected_phase, explain, run, Phase
from agent_contract.models import validate_pair

class MtuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=local_path((ROOT/'data/host1/mtu-replay/latest-run.txt').read_text().strip())
        cls.inputs={s:prepare_input(cls.directory/('L12-'+s+'.json')) for s in ('baseline','fault','recovered','partial')}
    def test_four_phase_boundaries(self):
        for case,want in (('baseline','baseline'),('fault','fault'),('recovered','recovered'),('partial','undetermined')):
            self.assertEqual(expected_phase(self.inputs[case][1]),want)
    def test_all_four_model_labels_available(self):
        self.assertEqual(set(Phase.model_json_schema()['properties']['phase']['enum']),{'baseline','fault','recovered','undetermined'})
    def test_current_mismatch_wins_over_partial_history(self):
        p=deepcopy(self.inputs['fault'][1]);p['history_complete']=False
        self.assertEqual(expected_phase(p),'fault')
    def test_restored_equality_without_previous_fault_is_not_recovered(self):
        p=deepcopy(self.inputs['recovered'][1]);p['observations']=p['observations'][-1:];p['history_complete']=False
        self.assertEqual(expected_phase(p),'undetermined')
    def test_equal_unusual_mtu_is_not_inequality(self):
        p=deepcopy(self.inputs['baseline'][1])
        for row in p['observations'][0]['endpoints']:row['mtu']=1400
        self.assertEqual(expected_phase(p),'baseline')
    def test_endpoint_order_does_not_change_mismatch(self):
        p=deepcopy(self.inputs['fault'][1])
        for obs in p['observations']:obs['endpoints'].reverse()
        self.assertEqual(expected_phase(p),'fault')
    def test_atomic_mtu_claim_uses_own_endpoint(self):
        req,p,_=self.inputs['fault'];result=explain(req,p,'fault');validate_pair(req.model_dump(),result)
        for obs in p['observations']:
            for endpoint,ident in zip(obs['endpoints'],obs['interface_refs']):
                claim=next(c for c in result['claims'] if c['evidence_ids']==[ident])
                self.assertIn(endpoint['node'],claim['statement']);self.assertIn('MTU='+str(endpoint['mtu']),claim['statement'])
    def test_healthy_peers_do_not_prove_no_mtu_mismatch(self):
        req,p,_=self.inputs['fault']
        self.assertEqual(expected_phase(p),'fault')
        self.assertTrue(all(json.loads(r.content)['physical']=='up' for r in req.evidence if r.id.endswith('G')))
    def test_existing_admin_down_profile_still_rejects_mtu_mismatch(self):
        from reasoning_agent.rca_gate import state_scope
        sequence=read(self.directory/'L12-fault.json')
        bundle=read(local_path(sequence['snapshots'][-1]['path']))
        with self.assertRaisesRegex(ValueError,'mtu_mismatch_outside_link_rca_profile'):
            state_scope(bundle['evidence'])
    def test_no_cause_patch_or_preferred_mtu_asserted(self):
        req,p,_=self.inputs['fault'];result=explain(req,p,'fault')
        self.assertFalse(result['execution_allowed']);self.assertEqual(result['proposed_patch'],[])
        self.assertIn('tidak membuktikan',result['root_cause_hypothesis'])
        self.assertIn('bukan bukti konfigurasi aktif',result['claims'][-1]['statement'])
    def test_negative_sources_rejected_without_model(self):
        class Trap:
            def generate(self,request):raise AssertionError('Must not call model')
        for kind in ('unknown_mtu','boolean_mtu','missing_endpoint','cross_link','reversed_time'):
            out=self.directory/'unit-artifacts'/(kind+'-'+uuid.uuid4().hex[:8])
            audit=run(self.directory/('L12-'+kind+'.json'),out,transport=Trap())
            self.assertFalse(audit['model_called']);self.assertEqual(audit['status'],'abstain')
    def test_wrong_model_phase_abstains_without_substitution(self):
        class Wrong:
            def generate(self,request):
                return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=8,response='{"phase":"recovered"}')
        out=self.directory/'unit-artifacts'/('wrong-'+uuid.uuid4().hex[:8])
        audit=run(self.directory/'L12-fault.json',out,transport=Wrong())
        prompt=read(out/'ollama-request.json')['prompt']
        data=json.loads(prompt.split('<|start_header_id|>user<|end_header_id|>\n\n')[1].split('<|eot_id|>')[0])
        self.assertEqual(data,dict(current_relation='UNEQUAL',earlier_relations=['EQUAL'],coverage='complete'))
        self.assertNotIn('phase',data)
        self.assertEqual(audit['raw_phase'],{'phase':'recovered'});self.assertEqual(audit['status'],'abstain')
        self.assertIn('model_phase_conflicts',audit['reason'])
        validate_pair(read(out/'input-contract.json'),read(out/'output-contract.json'))

if __name__=='__main__':unittest.main()
