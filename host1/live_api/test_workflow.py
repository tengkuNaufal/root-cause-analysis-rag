"""Workflow contracts with fake API/executor; no network or router commands."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from .capture import ROOT,write
from .examples import examples
from .workflow import run

class FakeClient:
    def __init__(self,session,synthetic=False):
        self.session=session;self.count=0;self.job_value=None;self.lost=False;self.synthetic=synthetic
    def submit(self,req):
        self.count+=1
        if self.lost:raise urllib.error.URLError('synthetic transport loss')
        job=examples()['hypothesis'];job['request_id']=req['request_id'];job['result']['request_id']=req['request_id']
        job['simulation']=self.synthetic;job['provenance']['synthetic']=self.synthetic
        path=self.session/job['job_id'];path.mkdir(parents=True,exist_ok=True);write(path/'response.json',job)
        self.job_value=job;return deepcopy(job)
    def job(self,jid):return deepcopy(self.job_value)
    def job_by_request(self,rid):return deepcopy(self.job_value)
    def evidence(self,url):return examples()['evidence']

class FakeExecutor:
    def __init__(self):self.calls=[]
    def run(self,path,output,apply=False,expected_sha256=None):
        self.calls.append(dict(apply=apply,expected_sha256=expected_sha256))
        return dict(status='verified' if apply else 'dry_run',applied=apply,verified=apply)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'private');self.base=Path(self.tmp.name)
        self.client=FakeClient(self.base/'session');self.executor=FakeExecutor()
    def tearDown(self):self.tmp.cleanup()
    def test_default_is_preview_and_resume_does_not_resubmit(self):
        result=run(self.client,self.base/'session',self.base/'run',executor=self.executor)
        self.assertEqual(result['status'],'dry_run');self.assertFalse(result['applied'])
        repeated=run(self.client,self.base/'session',self.base/'run',executor=self.executor)
        self.assertTrue(repeated['idempotent_replay']);self.assertEqual(self.client.count,1);self.assertEqual(len(self.executor.calls),1)
    def test_apply_requires_run_flag_and_binds_diagnosis_hash(self):
        result=run(self.client,self.base/'session',self.base/'run',apply=True,executor=self.executor)
        self.assertTrue(result['applied']);self.assertEqual(len(self.executor.calls[0]['expected_sha256']),64)
        self.assertFalse(result['diagnosis']['result']['execution_allowed'])
    def test_lost_post_with_lookup_missing_is_held_without_second_post(self):
        self.client.lost=True
        result=run(self.client,self.base/'session',self.base/'run',budget=.01,executor=self.executor)
        self.assertEqual(result['status'],'completion_unknown');self.assertEqual(self.executor.calls,[])
        run(self.client,self.base/'session',self.base/'run',budget=.01,executor=self.executor)
        self.assertEqual(self.client.count,1)
    def test_synthetic_diagnosis_never_reaches_executor(self):
        self.client.synthetic=True
        with self.assertRaises(ValueError):run(self.client,self.base/'session',self.base/'run',apply=True,executor=self.executor)
        self.assertEqual(self.executor.calls,[])

if __name__=='__main__':unittest.main()
