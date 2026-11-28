"""Authorized local executor. No HTTP apply route and no fault catalog dependency."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import time
from .capture import ROOT, ReadOnlyCapture, write
from .models import Job, canonical, digest, project
from .agent import DiagnosisEngine

class ExecutionError(ValueError):pass

def stable_id(fact):
    return (fact['type'],fact.get('link'),fact.get('router'),fact.get('key'))

class Executor:
    def __init__(self,capture=None,runner=None,verify=None,ledger_root=None):
        self.capture=capture or ReadOnlyCapture();self.runner=runner or subprocess.run
        self.verify=verify or self._verify
        self.ledger_root=Path(ledger_root) if ledger_root else ROOT/'private/live-executions'

    def _verify(self,output):
        output.mkdir(parents=True,exist_ok=False)
        deadline=time.monotonic()+60;attempt=0
        while time.monotonic()<deadline:
            attempt+=1;target=output/('attempt-'+str(attempt))
            try:
                p=self.runner([sys.executable,str(ROOT/'lab/host1/frr/verify-runtime.py'),str(target)],
                              capture_output=True,text=True,timeout=max(.1,deadline-time.monotonic()),check=False)
            except subprocess.TimeoutExpired:
                return False
            (output/('attempt-'+str(attempt)+'.log')).write_text(p.stdout+p.stderr)
            if p.returncode==0:
                fresh=self.capture.capture(output/'postconditions')
                return not any(f['anomaly'] for f in fresh['facts']['observations'])
            time.sleep(min(1,max(0,deadline-time.monotonic())))
        return False

    def run(self,diagnosis_path,output,apply=False,expected_sha256=None):
        from rca import linter
        from rca.topology import Topology
        diagnosis_path=Path(diagnosis_path).resolve();output=Path(output).resolve()
        if not diagnosis_path.is_relative_to(ROOT/'private') or not output.is_relative_to(ROOT/'private'):
            raise ExecutionError('Executor artifacts must stay under private/')
        original=diagnosis_path.read_bytes();sha=hashlib.sha256(original).hexdigest()
        if apply and sha!=expected_sha256:raise ExecutionError('Explicit diagnosis digest required for apply')
        job=Job.model_validate_json(original).root
        if job.simulation or job.state!='completed':raise ExecutionError('Only completed non-synthetic diagnosis can be applied')
        if job.result.status!='hypothesis' or not job.result.proposed_patch:
            return dict(status='not_requested',applied=False,verified=False,diagnosis_sha256=sha)
        commands=[c.model_dump() for c in project(job.result.proposed_patch)]
        lint=linter.lint(commands)
        if not lint['passed']:raise ExecutionError('Command linter rejected the plan')
        policy_file=Path(linter.__file__)
        policy_hash=linter.POLICY_SOURCE_SHA256
        if hashlib.sha256(policy_file.read_bytes()).hexdigest()!=policy_hash:
            raise ExecutionError('Loaded linter policy differs from source; restart executor')
        baseline_files={p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'lab/host1/frr/configs').glob('*/frr.conf')}
        output.mkdir(parents=True,exist_ok=False)
        result=dict(status='dry_run',applied=False,verified=False,diagnosis_sha256=sha,job_id=job.job_id,
            commands_sha256=digest(commands),commands=commands,lint=dict(status='passed',violations=[],
                policy_version=linter.POLICY_VERSION,policy_sha256=policy_hash),
            baseline_sources_sha256=baseline_files,command_results=[],execution_allowed_by_model=False)
        if not apply:
            write(output/'execution.json',result);return result
        # One executor per lab, including processes using different session directories.
        from scripts.lab_lock import lab_lock
        with lab_lock('rca'):
            ledger=self.ledger_root/(job.job_id+'.json')
            if not ledger.resolve().is_relative_to(ROOT/'private'):raise ExecutionError('Ledger must stay private')
            ledger.parent.mkdir(parents=True,exist_ok=True)
            if ledger.exists():
                receipt=json.loads(ledger.read_bytes())
                if receipt['diagnosis_sha256']!=sha:raise ExecutionError('Job execution digest conflict')
                if receipt['status']=='executing':raise ExecutionError('Prior execution completion is unknown; inspect lab before any retry')
                return {**receipt,'idempotent_replay':True,'fresh_verification':False}
            if diagnosis_path.read_bytes()!=original:raise ExecutionError('Diagnosis changed before execution')
            if hashlib.sha256(policy_file.read_bytes()).hexdigest()!=policy_hash:raise ExecutionError('Policy changed')
            index=json.loads((diagnosis_path.parent/'evidence-index.json').read_bytes())
            DiagnosisEngine._verify_sources(diagnosis_path.parent,index)
            manifests={e.id:e for e in job.evidence}
            for ref in index:
                manifest=manifests.get(ref['payload']['id'])
                if manifest is None or any(ref['payload'][k]!=getattr(manifest,k) for k in ('kind','source_id','source_sha256','locator')):
                    raise ExecutionError('Evidence manifest binding changed')
            used=set(job.assessment.evidence_ids)
            old=json.loads((diagnosis_path.parent/'facts.json').read_bytes())
            if old.get('baseline_sources_sha256')!=baseline_files:raise ExecutionError('Baseline configuration changed')
            observed=self.capture.capture(output/'preconditions')
            current={stable_id(f):f for f in observed['facts']['observations'] if f['type'] in ('setting','physical')}
            checked=0
            for ref in index:
                if ref['payload']['id'] not in used or ref['payload']['kind']!='telemetry':continue
                locator=ref['payload']['locator']
                if not locator.startswith('/observations/'):continue
                f=old['observations'][int(locator.rsplit('/',1)[1])]
                if f['type'] not in ('setting','physical'):continue
                if current.get(stable_id(f))!=f:raise ExecutionError('Cited network precondition changed')
                checked+=1
            if not checked:raise ExecutionError('No stable network preconditions bound to plan')
            # Re-lint immediately before dispatch; model/lint flags never grant authorization.
            if hashlib.sha256(policy_file.read_bytes()).hexdigest()!=policy_hash:raise ExecutionError('Policy changed during preflight')
            if not linter.lint(commands)['passed']:raise ExecutionError('Linter changed decision')
            result.update(status='executing',authorized_by_local_operator=True,preconditions_checked=checked)
            write(output/'execution.json',result);write(ledger,result)
            try:
                for cmd in commands:
                    if cmd['interpreter']=='ip':argv=['ip',*cmd['args']]
                    else:
                        argv=['vtysh']
                        for line in cmd['args']:argv+=['-c',line]
                    args=['docker','exec','clab-rca-'+cmd['router'],*argv]
                    result['execution_attempted']=True
                    p=self.runner(args,capture_output=True,text=True,timeout=20,check=False)
                    notes=[line for line in p.stdout.splitlines() if line.lstrip().startswith('%') and not line.lstrip().startswith('% Configuration applied with notes')]
                    invalid_cli=re.search(r'unknown command|ambiguous command|incomplete command',p.stdout+'\n'+p.stderr,re.I)
                    result['command_results'].append(dict(router=cmd['router'],returncode=p.returncode,
                        stdout=p.stdout,stderr=p.stderr));result['applied']=True
                    write(output/'execution.json',result)
                    if p.returncode or notes or invalid_cli:raise ExecutionError('Router rejected a command; partial application possible')
                result['verified']=bool(self.verify(output/'verification'))
                result['status']='verified' if result['verified'] else 'verification_failed'
            except Exception as exc:
                if isinstance(exc,subprocess.TimeoutExpired):result['applied']=None
                result.update(status='execution_error',error=type(exc).__name__+': '+str(exc))
                # Still observe network after partial application. No hidden catalog revert.
                try:result['verified']=bool(self.verify(output/'verification-after-error'))
                except Exception:result['verified']=False
            result['completed_at_utc']=datetime.now(timezone.utc).isoformat()
            write(output/'execution.json',result);write(ledger,result)
            return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('diagnosis',type=Path);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--apply',action='store_true');ap.add_argument('--expected-diagnosis-sha256')
    args=ap.parse_args()
    result=Executor().run(args.diagnosis,args.output,args.apply,args.expected_diagnosis_sha256)
    print(json.dumps(result,indent=2))
    return 0 if result['status'] in ('not_requested','dry_run','verified') else 2

if __name__=='__main__':raise SystemExit(main())
