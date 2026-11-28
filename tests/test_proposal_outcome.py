import copy
import json
import math

import pytest

from scripts.proposal_outcome import PREFIX, rejection_note, read_rejection
from rca.evaluator import evaluate, score_run
from tests.test_evaluator_live import host2_row


def rejected_row(stage='guard'):
    row=host2_row()
    job=row['diagnosis'];candidate=copy.deepcopy(job['assessment']['commands'])
    code='proposed_patch_rejected_by_linter' if stage=='lint' else 'proposal_does_not_restore_observed_baseline'
    job['result']['missing_evidence']=[rejection_note(stage,code,candidate,'host1-policy-v2')]
    job['result']['proposed_patch']=[];job['assessment']['commands']=[]
    job['provenance']['model_evidence_ids']=['e1']
    row['proposal']=read_rejection(job)
    row['lint']={'status':'not_requested','violations':[],'commands_sha256':None}
    row['fallback_revert']['reason']='api_proposal_rejected'
    return row


@pytest.mark.parametrize('stage',['lint','guard'])
def test_correct_diagnosis_is_independent_of_proposal_rejection(catalog,linter,stage):
    scored=score_run(rejected_row(stage),catalog,linter)
    assert scored['rca_ok'] and scored['router_ok'] and scored['class_ok']
    assert not scored['agent_error'] and not scored['abstain'] and not scored['incomplete_prediction']
    assert scored['proposal_rejected'] and scored['proposal_rejection_stage']==stage
    assert scored['candidate_commands_count']==1 and not scored['has_commands']
    assert not scored['lint_passed'] and not scored['command_approved'] and not scored['cmd_ok']
    assert not scored['agent_recovered'] and scored['t_recovery_s'] is None
    assert not scored['halluc_evidence'] and scored['rejected_candidate_hallucination_unassessed']


def test_report_separates_accuracy_rejection_approval_and_recovery(tmp_path):
    path=tmp_path/'runs.jsonl';path.write_text(json.dumps(rejected_row()))
    result=evaluate(path,tmp_path/'out');m=result['metrics'].iloc[0]
    assert m['rca_accuracy']==1 and m['proposal_guard_rejection_rate']==1
    assert m['proposal_rejection_rate']==1 and m['proposal_lint_rejection_rate']==0
    assert m['command_approval_rate']==0 and m['command_correctness']==0
    assert math.isnan(m['fix_success_rate']) and m['agent_error_rate']==0
    assert 'Proposal dan validasi perintah' in (tmp_path/'out/report.md').read_text()


def test_empty_proposal_without_note_is_not_a_rejection(catalog,linter):
    row=host2_row();row['diagnosis']['result']['proposed_patch']=[];row['diagnosis']['assessment']['commands']=[]
    row['lint']={'status':'not_requested'}
    scored=score_run(row,catalog,linter)
    assert scored['rca_ok'] and not scored['proposal_rejected'] and not scored['command_approved']


def test_evaluator_does_not_infer_a_rejection_for_old_failed_job(catalog,linter):
    scored=score_run(host2_row('failed'),catalog,linter)
    assert scored['agent_error'] and not scored['rca_ok'] and not scored['proposal_rejected']


@pytest.mark.parametrize('field,value',[('applied',True),('execution',{'attempted':True}),
                                      ('proposal',{'status':'rejected','stage':'invented'})])
def test_inconsistent_runner_metadata_rejected(catalog,linter,field,value):
    row=rejected_row();row[field]=value
    with pytest.raises(ValueError):score_run(row,catalog,linter)


@pytest.mark.parametrize('field,value',[('version',2),('stage','unknown'),('code','arbitrary_error'),
    ('candidate_count',0),('candidate_count',True),('commands_sha256','bad'),('policy_version','')])
def test_decoder_rejects_malformed_metadata(field,value):
    job=rejected_row()['diagnosis'];note=json.loads(job['result']['missing_evidence'][0][len(PREFIX):])
    note[field]=value;job['result']['missing_evidence']=[PREFIX+json.dumps(note)]
    with pytest.raises(ValueError):read_rejection(job)


def test_candidate_hash_matches_runner_canonicalization():
    from scripts.live_client import canonical_sha256
    row=host2_row();commands=row['diagnosis']['assessment']['commands']
    note=rejection_note('lint','proposed_patch_rejected_by_linter',commands,'host1-policy-v2')
    assert json.loads(note[len(PREFIX):])['commands_sha256']==canonical_sha256(commands)
