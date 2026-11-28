"""Coverage for all ten diagnosis labels and authorized dispatch; every router is fake."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from .test_agent import FixtureCapture,FixtureModel,engine,run_engine
from .agent import DiagnosisEngine
from .capture import ROOT
from .executor import Executor,ExecutionError
from .models import Job
from .settings import parse,differences,supports

CASES=[
 ('ospf_hello_mismatch','r2',' ip ospf hello-interval 1',' ip ospf hello-interval 2'),
 ('ospf_area_mismatch','r1',' ip ospf area 0.0.0.0',' ip ospf area 0.0.0.1'),
 ('ospf_auth_mismatch','r1','interface eth1\n','interface eth1\n ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 SECRET\n'),
 ('bgp_neighbor_shutdown','r3',' neighbor 10.0.35.2 remote-as 65002',' neighbor 10.0.35.2 remote-as 65002\n neighbor 10.0.35.2 shutdown'),
 ('bgp_wrong_remote_as','r4',' neighbor 10.0.46.2 remote-as 65003',' neighbor 10.0.46.2 remote-as 65103'),
 ('bgp_missing_network','r5','  network 10.100.5.1/32',''),
 ('wrong_ip_address','r1',' ip address 10.0.12.1/30',' ip address 10.0.212.1/30'),
 ('bgp_inbound_filter','r3','! Baseline RCA lab;', '! Baseline RCA lab;'),
]

class ExtendedTests(unittest.TestCase):
    def test_eight_configuration_classes_have_citable_observed_support(self):
        for cause,router,a,b in CASES:
            with self.subTest(cause=cause):
                cap=FixtureCapture();orig=cap.runner
                def command(args,**kwargs):
                    p=orig(args,**kwargs)
                    if args[:2]==['docker','exec'] and args[2]=='clab-rca-'+router:
                        text=p.stdout
                        if cause=='bgp_inbound_filter':text+='\nip prefix-list FAULT_IN seq 5 permit 10.100.5.1/32\nroute-map PEER1_IN deny 5\n match ip address prefix-list FAULT_IN\n'
                        else:
                            if a not in text and cause=='bgp_missing_network':a2=' network 10.100.5.1/32';text=text.replace(a2,b,1)
                            else:text=text.replace(a,b,1)
                        p=subprocess.CompletedProcess(args,0,text,'')
                    return p
                cap.runner=command
                eng=DiagnosisEngine(capture=cap,model=FixtureModel(cause=cause,router=router))
                with tempfile.TemporaryDirectory() as tmp:
                    job=run_engine(eng,tmp)
                self.assertEqual(job['result']['root_cause_class'],cause)
                self.assertEqual(job['result']['root_cause_router'],router)

    def test_authentication_values_are_not_stored_in_setting_diffs(self):
        base=parse('interface eth1\n ip ospf area 0\n')
        current=parse('interface eth1\n ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 SECRET\n')
        diff=differences('r1',base,current)
        self.assertNotIn('SECRET',json.dumps(diff));self.assertTrue(any(supports('ospf_auth_mismatch',f) for f in diff))

class ProposingModel(FixtureModel):
    def generate(self,payload):
        raw=super().generate(payload);value=json.loads(raw['response'])
        value['proposed_patch']=[dict(router='r1',interface='eth1',interpreter='linux_argv',arguments=['ip','link','set','eth1','mtu','1500'],evidence_ids=['e1'],rationale='Restore the expected MTU.',validation_status='unvalidated')]
        raw['response']=json.dumps(value);return raw

class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private')
        self.base=Path(self.tmp.name);self.eng=engine(model=ProposingModel())
        self.job=run_engine(self.eng,self.base)
        self.path=next(self.base.glob('*/response.json'))
        self.sha=hashlib.sha256(self.path.read_bytes()).hexdigest();self.calls=[]
        def command(args,**kwargs):
            self.calls.append(args)
            return subprocess.CompletedProcess(args,0,'','')
        self.executor=Executor(capture=FixtureCapture(fault='mtu'),runner=command,verify=lambda _:True,ledger_root=self.base/'ledger')
    def tearDown(self):self.tmp.cleanup()
    def test_dry_run_does_not_dispatch(self):
        r=self.executor.run(self.path,self.base/'dry');self.assertEqual(r['status'],'dry_run');self.assertFalse(r['applied']);self.assertEqual(self.calls,[])
    def test_digest_authorization_required(self):
        with self.assertRaises(ExecutionError):self.executor.run(self.path,self.base/'invalid',True,'0'*64)
        self.assertEqual(self.calls,[])
    def test_authorized_bound_dispatch_verify_and_idempotency(self):
        result=self.executor.run(self.path,self.base/'apply',True,self.sha)
        self.assertEqual(result['status'],'verified');self.assertTrue(result['applied']);self.assertTrue(result['verified'])
        self.assertEqual(self.calls,[['docker','exec','clab-rca-r1','ip','link','set','eth1','mtu','1500']])
        again=self.executor.run(self.path,self.base/'repeat',True,self.sha)
        self.assertTrue(again['idempotent_replay']);self.assertEqual(len(self.calls),1)
    def test_changed_precondition_blocks_dispatch(self):
        self.executor.capture=FixtureCapture()
        with self.assertRaises(ExecutionError):self.executor.run(self.path,self.base/'changed',True,self.sha)
        self.assertEqual(self.calls,[])
    def test_synthetic_job_and_changed_source_rejected(self):
        raw=json.loads(self.path.read_bytes());raw['simulation']=True;raw['provenance']['synthetic']=True;self.path.write_text(json.dumps(raw))
        with self.assertRaises(ExecutionError):self.executor.run(self.path,self.base/'synthetic')
    def test_command_failure_records_partial_application_and_verifies(self):
        self.executor.runner=lambda args,**kwargs:subprocess.CompletedProcess(args,1,'','synthetic failure')
        result=self.executor.run(self.path,self.base/'fail',True,self.sha)
        self.assertEqual(result['status'],'execution_error');self.assertTrue(result['applied']);self.assertTrue(result['verified'])
    def test_timeout_reports_unknown_application(self):
        def timeout(args,**kwargs):raise subprocess.TimeoutExpired(args,20)
        self.executor.runner=timeout
        result=self.executor.run(self.path,self.base/'timeout',True,self.sha)
        self.assertEqual(result['status'],'execution_error');self.assertIsNone(result['applied'])
    def test_linter_policy_has_version(self):
        from rca.linter import POLICY_VERSION
        self.assertTrue(POLICY_VERSION)

if __name__=='__main__':unittest.main()
