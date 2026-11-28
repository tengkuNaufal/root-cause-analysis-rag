"""One diagnosis -> evidence -> lint -> optional authorized apply -> verification; no injection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
from scripts.live_client import LiveClient,new_request,utc_now,TRANSPORT_ERRORS,ApiError,verify_evidence
from .capture import ROOT,write
from .executor import Executor
from .models import Job,canonical

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def checkpoint(path,value):
    path=Path(path);temp=path.with_name(path.name+'.tmp')
    with temp.open('wb') as handle:
        handle.write(canonical(value));handle.flush();os.fsync(handle.fileno())
    os.replace(temp,path)


def run(client,session,output,variant='graph_rag',apply=False,budget=180,executor=None):
    session=Path(session).resolve();output=Path(output).resolve()
    if not session.is_relative_to(ROOT/'private') or not output.is_relative_to(ROOT/'private'):
        raise ValueError('Workflow paths must be private')
    output.mkdir(parents=True,exist_ok=True)
    reqfile=output/'request.json';fresh=not reqfile.exists()
    req=new_request(variant,utc_now()) if fresh else json.loads(reqfile.read_bytes())
    if req['variant']!=variant:raise ValueError('Resume variant mismatch')
    if fresh:checkpoint(reqfile,req)
    final=output/'workflow.json'
    if final.exists():
        previous=json.loads(final.read_bytes())
        if previous['status'] not in ('completion_unknown',) and not (apply and previous['status']=='dry_run'):
            return {**previous,'idempotent_replay':True}
    deadline=time.monotonic()+budget;job=None
    if fresh:
        try:job=client.submit(req)
        except TRANSPORT_ERRORS:pass
        except ApiError as exc:
            if exc.status<500 or exc.code in ('agent_busy','live_not_ready','replay_session_reserved'):
                result=dict(status='admission_error',applied=False,request_id=req['request_id'],error=exc.code)
                checkpoint(output/'workflow.json',result);return result
    while time.monotonic()<deadline:
        try:
            job=client.job(job['job_id']) if job else client.job_by_request(req['request_id'])
        except (ApiError,*TRANSPORT_ERRORS):
            time.sleep(1);continue
        if job and job.get('state') in ('completed','failed','interrupted'):break
        time.sleep(1)
    if not job or job.get('state') not in ('completed','failed','interrupted'):
        result=dict(status='completion_unknown',applied=False,request_id=req['request_id'])
        checkpoint(output/'workflow.json',result);return result
    validated=Job.model_validate(job).root
    if validated.request_id!=req['request_id'] or validated.variant!=variant or validated.simulation:
        raise ValueError('Job is not bound to this real request')
    if validated.state!='completed':
        result=dict(status='diagnosis_failed',applied=False,diagnosis=job)
        checkpoint(output/'workflow.json',result);return result
    evidence=verify_evidence(client,job)
    if evidence['problems'] or not evidence['total']:raise ValueError('Evidence verification failed')
    original=session/validated.job_id/'response.json'
    if canonical(json.loads(original.read_bytes()))!=canonical(job):raise ValueError('Local/API diagnosis mismatch')
    executor=executor or Executor()
    # --apply grants run-level operator authorization; a model flag never does.
    receipt=executor.run(original,output/('apply' if apply else 'preview'),apply=apply,
        expected_sha256=hashlib.sha256(original.read_bytes()).hexdigest() if apply else None)
    result=dict(status=receipt['status'],request_id=req['request_id'],job_id=validated.job_id,
                diagnosis=job,evidence_check=evidence,execution=receipt,applied=receipt['applied'])
    checkpoint(output/'workflow.json',result);return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--session',type=Path,required=True,help='Private API jobs directory')
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--variant',choices=['zero_shot','text_rag','graph_rag'],default='graph_rag')
    ap.add_argument('--apply',action='store_true',help='Authorize this single workflow to apply linted commands locally')
    args=ap.parse_args()
    client=LiveClient('http://127.0.0.1:8766',os.environ.get('LIVE_API_TOKEN',''))
    client._opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    result=run(client,args.session,args.output,args.variant,args.apply)
    print(json.dumps({k:v for k,v in result.items() if k not in ('diagnosis','execution')},indent=2))
    return 0 if result['status'] in ('not_requested','dry_run','verified') else 2

if __name__=='__main__':raise SystemExit(main())
