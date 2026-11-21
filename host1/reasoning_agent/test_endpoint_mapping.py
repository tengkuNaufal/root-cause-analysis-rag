"""Source binding, nuisance-factor isolation, and no-repair checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from knowledge.evidence import ROOT, read
from reasoning_agent.temporal import (endpoint_input,context_input,validate_endpoint,EndpointState,
    grouped_request,run)
from reasoning_agent import test_temporal as temporal_tests
from reasoning_agent.freeze_endpoint_cases import id_map

class EndpointMappingTests(temporal_tests.TemporalTests):
    def test_per_node_inputs_invariant_to_order_and_citation_ids(self):
        for name in ('L12-down','L35-down','L12-restored','L35-before'):
            _,_,base,_,_=self.selected(name)
            _,_,changed,_,_=self.selected(name,reverse_endpoints=True,citation_map=id_map(97123))
            inputs=lambda p:{r['node']:endpoint_input(r) for r in p['current']['interfaces']}
            self.assertEqual(inputs(base),inputs(changed))
            self.assertEqual(context_input(base),context_input(changed))
            self.assertNotEqual(base['required_current_refs'],changed['required_current_refs'])

    def test_output_boolean_values_are_not_schema_constants(self):
        schema=EndpointState.model_json_schema()
        self.assertNotIn('const',schema['properties']['admin_up'])
        self.assertNotIn('enum',schema['properties']['admin_up'])
        self.assertNotIn('const',schema['properties']['carrier_up'])

    def test_wrong_bound_boolean_is_rejected_not_repaired(self):
        _,_,payload,_,_=self.selected('L12-down',reverse_endpoints=True)
        row=payload['current']['interfaces'][0]
        self.assertEqual(row['node'],'r2:eth1');self.assertIs(row['admin_up'],True)
        value=dict(admin_up=False,carrier_up=False,peer_state='absent')
        with self.assertRaisesRegex(ValueError,'endpoint_value_conflicts'):
            validate_endpoint(value,row)
        self.assertIs(value['admin_up'],False)

    def test_identity_is_not_a_model_selected_response_field(self):
        _,_,payload,_,_=self.selected('L12-down')
        value=dict(node='r2:eth1',admin_up=False,carrier_up=False,peer_state='absent')
        with self.assertRaises(ValueError):validate_endpoint(value,payload['current']['interfaces'][0])

    def test_citation_alias_collision_rejected(self):
        mapping=id_map(97123);mapping['T2']=mapping['T1']
        with self.assertRaisesRegex(ValueError,'invalid_citation_map'):
            self.selected('L35-down',citation_map=mapping)

    def test_grouped_baseline_request_matches_previous_saved_request(self):
        old=ROOT/'data/host1/llm-temporal/20261120T124951Z/dev-v5/d2'
        payload=read(old/'visible-evidence.json');profile=read(ROOT/'host1/ollama_host/inference-profile.json')
        request,budget=grouped_request(payload,profile)
        self.assertEqual(request,read(old/'observation-request.json'))

    def test_wrong_endpoint_value_stops_before_phase_without_substitution(self):
        class WrongCopy:
            def generate(self,request):
                return dict(done=True,done_reason='stop',prompt_eval_count=100,eval_count=50,
                    response=json.dumps(dict(admin_up=False,carrier_up=True,peer_state='Full/-')))
        with tempfile.TemporaryDirectory(dir=ROOT/'data/host1') as directory:
            audit=run(ROOT/'data/host1/evidence-retrieval/replay-final-20261119/L12-before.json',
                      Path(directory)/'out',transport=WrongCopy(),extractor='bound')
            self.assertTrue(audit['model_called']);self.assertEqual(audit['llm_requests'],1)
            self.assertEqual(audit['status'],'abstain');self.assertNotIn('raw_phase_prediction',audit)

if __name__=='__main__':unittest.main()
