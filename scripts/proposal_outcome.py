"""Versioned rejection note carried in existing wire fields; stdlib only, no execution."""
import hashlib
import json
import re

PREFIX = 'proposal_rejected:v1:'
REJECTIONS = {
    'lint': {'proposed_patch_rejected_by_linter'},
    'guard': {'mtu_check_bypass_is_not_baseline_repair', 'vtysh_configuration_mode_required',
              'proposal_does_not_restore_observed_baseline'},
}


def rejection_note(stage, code, commands, policy_version):
    if code not in REJECTIONS.get(stage, ()) or not commands:
        raise ValueError('Invalid proposal rejection')
    digest = hashlib.sha256(json.dumps(commands, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()
    payload = dict(version=1, status='rejected', stage=stage, code=code,
                   commands_sha256=digest, candidate_count=len(commands), policy_version=policy_version)
    return PREFIX + json.dumps(payload, sort_keys=True, separators=(',', ':'))


def read_rejection(job):
    result = job.get('result') or {}
    notes = result.get('missing_evidence') or []
    markers = [s for s in notes if isinstance(s, str) and s.startswith('proposal_rejected:')]
    if not markers:
        return None
    if len(markers) != 1 or not markers[0].startswith(PREFIX):
        raise ValueError('Unknown or duplicate proposal rejection note')
    try:
        value = json.loads(markers[0][len(PREFIX):])
        required = {'version', 'status', 'stage', 'code', 'commands_sha256', 'candidate_count', 'policy_version'}
        valid = (isinstance(value, dict) and set(value) == required and type(value['version']) is int
                 and value['version'] == 1 and value['status'] == 'rejected'
                 and value['code'] in REJECTIONS.get(value['stage'], ())
                 and isinstance(value['commands_sha256'], str) and re.fullmatch('[0-9a-f]{64}', value['commands_sha256'])
                 and type(value['candidate_count']) is int and value['candidate_count'] > 0
                 and isinstance(value['policy_version'], str) and bool(value['policy_version']))
    except (ValueError, KeyError, TypeError):
        raise ValueError('Invalid proposal rejection note') from None
    if not valid:
        raise ValueError('Invalid proposal rejection note')
    assessment = job.get('assessment') or {}
    if (job.get('state') != 'completed' or result.get('status') != 'hypothesis'
            or result.get('root_cause_class') in (None, 'unknown') or not result.get('claims')
            or result.get('proposed_patch') != [] or assessment.get('commands') != []):
        raise ValueError('Proposal rejection must preserve a hypothesis and export no commands')
    return value
