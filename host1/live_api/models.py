"""Wire schema, independent of the active replay contract and server."""
from datetime import datetime
import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, RootModel, field_validator, model_validator
from agent_contract.models import Strict, Response, Request as AgentRequest, validate_pair

VERSION = 'live.v1-draft2'
Router = Literal['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
Variant = Literal['zero_shot', 'text_rag', 'graph_rag']
Cause = Literal['mtu_mismatch', 'link_down', 'ospf_hello_mismatch', 'ospf_area_mismatch',
                'ospf_auth_mismatch', 'bgp_neighbor_shutdown', 'bgp_wrong_remote_as',
                'bgp_inbound_filter', 'bgp_missing_network', 'wrong_ip_address', 'unknown']
Id = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]
Sha = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Stamp = Annotated[str, Field(pattern=r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$')]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]

def timestamp(value):
    datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

class DiagnosisRequest(Strict):
    contract_version: Literal['live.v1-draft2']
    request_id: Id
    lab: Literal['rca']
    variant: Variant
    symptom_detected_at_utc: Stamp
    execution_allowed: Literal[False]

    @field_validator('execution_allowed', mode='before')
    @classmethod
    def boolean_only(cls, v):
        if type(v) is not bool:
            raise ValueError('execution_allowed must be a JSON boolean')
        return v

    @field_validator('request_id')
    @classmethod
    def valid_uuid(cls, v):
        UUID(v)
        return v

    @field_validator('symptom_detected_at_utc')
    @classmethod
    def valid_time(cls, v):
        return timestamp(v)

class Command(Strict):
    router: Router
    interpreter: Literal['ip', 'vtysh']
    args: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)

    @field_validator('args')
    @classmethod
    def no_shell(cls, args):
        if any(any(c in a for c in (';', '|', '&', '\n', '\r', '\x00', '`', '$(')) for a in args):
            raise ValueError('Shell syntax is not a wire command')
        return args

def project(patch):
    commands = []
    for p in patch:
        if p.interpreter == 'vtysh_commands':
            interpreter, args = 'vtysh', p.arguments
        elif p.arguments[0] == 'ip' and len(p.arguments) > 1:
            interpreter, args = 'ip', p.arguments[1:]
        else:
            raise ValueError('Patch cannot be projected to wire commands')
        commands.append(Command(router=p.router, interpreter=interpreter, args=args))
    return commands

class Assessment(Strict):
    router: Router | None
    root_cause: Cause
    confidence: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_ids: list[str]
    commands: list[Command]
    explanation: str = Field(min_length=1)

class EvidencePayload(Strict):
    id: str = Field(pattern=r'^e[0-9]+$')
    kind: Literal['telemetry', 'log', 'graph', 'documentation']
    source_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    source_sha256: Sha
    locator: str = Field(min_length=1)
    content: str = Field(min_length=1)

    @model_validator(mode='after')
    def consistent_source(self):
        if self.source_id != 'sha256:' + self.source_sha256:
            raise ValueError('Source ID/hash mismatch')
        return self

class Evidence(EvidencePayload):
    # Manifest excludes content; use manifest() when forming the wire envelope.
    url: str = Field(pattern=r'^/v1/diagnoses/[0-9a-f-]{36}/evidence/e[0-9]+$')
    capture_started_at: Stamp
    capture_completed_at: Stamp

    @model_validator(mode='after')
    def capture_order(self):
        timestamp(self.capture_started_at); timestamp(self.capture_completed_at)
        if datetime.fromisoformat(self.capture_started_at.replace('Z', '+00:00')) > datetime.fromisoformat(self.capture_completed_at.replace('Z', '+00:00')):
            raise ValueError('Capture timestamps reversed')
        return self

class EvidenceManifest(Strict):
    id: str = Field(pattern=r'^e[0-9]+$')
    kind: Literal['telemetry', 'log', 'graph', 'documentation']
    source_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    source_sha256: Sha
    locator: str = Field(min_length=1)
    url: str = Field(pattern=r'^/v1/diagnoses/[0-9a-f-]{36}/evidence/e[0-9]+$')
    capture_started_at: Stamp
    capture_completed_at: Stamp

    @model_validator(mode='after')
    def valid_manifest(self):
        Evidence.model_validate({**self.model_dump(), 'content': 'manifest-only validation'})
        return self

class Timing(Strict):
    collection_seconds: Seconds
    retrieval_seconds: Seconds
    reasoning_seconds: Seconds
    validation_seconds: Seconds
    total_seconds: Seconds

class Provenance(Strict):
    synthetic: bool
    inventory_sha256: Sha
    capture_sha256: Sha
    agent_version: str
    gate_version: str
    prompt_version: str
    retriever_version: str
    model_profile: str
    model_digest: Sha
    model_options: dict[str, int | str | float | bool]
    actual_variant: Variant
    model_evidence_ids: list[str]
    selection_notes: list[str]
    evidence_age_at_reasoning_seconds: Seconds
    evidence_age_at_completion_seconds: Seconds

class Error(Strict):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool

class ErrorResponse(Strict):
    contract_version: Literal['live.v1-draft2']
    request_id: Id | None
    error: Error

class WireResponse(Response):
    # Required on the live wire, independent of proposal targets and replay v1.
    root_cause_class: Cause | None
    root_cause_router: Router | None

    @model_validator(mode='after')
    def diagnosis_labels(self):
        if self.status == 'abstain':
            if self.root_cause_class is not None or self.root_cause_router is not None:
                raise ValueError('Abstain cannot assign diagnosis labels')
        elif self.root_cause_class is None:
            raise ValueError('Hypothesis needs a class or explicit unknown')
        return self

    @field_validator('execution_allowed', mode='before')
    @classmethod
    def boolean_only(cls, v):
        if type(v) is not bool:
            raise ValueError('execution_allowed must be a JSON boolean')
        return v

def validate_live_pair(request, response):
    """Apply replay-v1 evidence/gate guards without adding fields to that contract."""
    req = AgentRequest.model_validate(request)
    if req.mode != 'live':
        raise ValueError('Live response requires live input')
    res = WireResponse.model_validate(response)
    validate_pair(req.model_dump(), res.model_dump(exclude={'root_cause_class', 'root_cause_router'}))
    return res

class Envelope(Strict):
    contract_version: Literal['live.v1-draft2']
    request_id: Id
    job_id: Id
    mode: Literal['live']
    lab: Literal['rca']
    variant: Variant
    received_at: Stamp
    updated_at: Stamp
    execution_allowed: Literal[False]
    simulation: bool

    @field_validator('execution_allowed', mode='before')
    @classmethod
    def boolean_only(cls, v):
        if type(v) is not bool:
            raise ValueError('execution_allowed must be a JSON boolean')
        return v

    @field_validator('received_at', 'updated_at')
    @classmethod
    def time_fields(cls, v):
        return timestamp(v)

class Pending(Envelope):
    state: Literal['accepted', 'collecting', 'reasoning']

class Completed(Envelope):
    state: Literal['completed']
    result: WireResponse
    assessment: Assessment
    evidence: list[EvidenceManifest] = Field(min_length=1)
    timing: Timing
    provenance: Provenance

    @model_validator(mode='after')
    def bindings(self):
        ids = {e.id for e in self.evidence}
        used = {i for c in [*self.result.claims, *self.result.proposed_patch] for i in c.evidence_ids}
        if len(ids) != len(self.evidence) or not used <= ids or set(self.assessment.evidence_ids) != used:
            raise ValueError('Evidence bindings invalid')
        if len(self.assessment.evidence_ids) != len(set(self.assessment.evidence_ids)):
            raise ValueError('Duplicate assessment references')
        if self.result.request_id != self.request_id or self.assessment.confidence != self.result.confidence:
            raise ValueError('Agent/assessment mismatch')
        if (self.assessment.router != self.result.root_cause_router or
                self.assessment.root_cause != (self.result.root_cause_class or 'unknown')):
            raise ValueError('Diagnosis labels/assessment mismatch')
        if self.assessment.commands != project(self.result.proposed_patch):
            raise ValueError('Command projection mismatch')
        if self.provenance.actual_variant != self.variant or not set(self.provenance.model_evidence_ids) <= ids:
            raise ValueError('Provenance mismatch')
        if self.simulation != self.provenance.synthetic:
            raise ValueError('Simulation mismatch')
        for e in self.evidence:
            if e.url != f'/v1/diagnoses/{self.job_id}/evidence/{e.id}':
                raise ValueError('Foreign evidence URL')
        if self.result.status == 'abstain' and (self.assessment.router is not None or self.assessment.root_cause != 'unknown'):
            raise ValueError('Abstain cannot assign blame')
        return self

class Failed(Envelope):
    state: Literal['failed', 'interrupted']
    error: Error

class Job(RootModel[Annotated[Pending | Completed | Failed, Field(discriminator='state')]]):
    pass

class LintInput(Strict):
    contract_version: Literal['live.v1-draft2']
    job_id: Id
    inventory_sha256: Sha
    commands: list[Command] = Field(min_length=1)
    commands_sha256: Sha

    @model_validator(mode='after')
    def hash_matches(self):
        if digest([c.model_dump() for c in self.commands]) != self.commands_sha256:
            raise ValueError('Command hash mismatch')
        return self

class Violation(Strict):
    command_index: int | None = Field(ge=0)
    code: str
    message: str

class LintOutput(Strict):
    job_id: Id
    commands_sha256: Sha
    inventory_sha256: Sha
    linter_version: str
    policy_version: str
    policy_sha256: Sha
    status: Literal['passed', 'rejected', 'error']
    violations: list[Violation]
    checked_at: Stamp

    @model_validator(mode='after')
    def lint_state(self):
        timestamp(self.checked_at)
        if self.status == 'passed' and self.violations:
            raise ValueError('Passed lint has violations')
        if self.status == 'rejected' and not self.violations:
            raise ValueError('Rejected lint needs violations')
        return self

def validate_lint_pair(request, response):
    req, res = LintInput.model_validate(request), LintOutput.model_validate(response)
    for key in ('job_id', 'commands_sha256', 'inventory_sha256'):
        if getattr(req, key) != getattr(res, key):
            raise ValueError('Lint binding mismatch')
    if any(v.command_index is not None and v.command_index >= len(req.commands) for v in res.violations):
        raise ValueError('Violation index out of range')
    return res

class Health(Strict):
    status: Literal['ok']
    mode: Literal['mock_live']
    simulation: Literal[True]
    active: bool
    ready: bool
    execution_allowed: Literal[False]

class FreshnessPolicy(Strict):
    max_age_seconds: Literal[15]
    max_skew_seconds: Literal[5]
    clock: Literal['host1']

class Readiness(Strict):
    mock: bool
    collector: Literal[False]
    model: Literal[False]
    linter: Literal[False]
    executor: Literal[False]

class Capabilities(Strict):
    contract_version: Literal['live.v1-draft2']
    mode: Literal['mock_live']
    simulation: Literal[True]
    lab: Literal['rca']
    variants: list[Variant]
    real_variants_available: list[Variant] = Field(max_length=0)
    model_profile: Literal['not_used']
    model_digest: Sha
    inventory_sha256: Sha
    max_body_bytes: Literal[4096]
    client_timeout_seconds: Literal[180]
    poll_seconds: Literal[1]
    server_deadline_seconds: Seconds
    retention_seconds: Literal[604800]
    freshness_policy: FreshnessPolicy
    readiness: Readiness
    note: str
