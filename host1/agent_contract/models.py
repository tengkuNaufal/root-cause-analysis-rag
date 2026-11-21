"""Strict Pydantic contract for future reasoning; all commands remain proposals."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Reference(Strict):
    id: str = Field(min_length=1)
    kind: Literal['telemetry', 'log', 'graph', 'documentation']
    source_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    locator: str = Field(min_length=1)
    content: str = Field(min_length=1)

class Gate(Strict):
    version: str
    decision: Literal['context_ready', 'abstain']
    answer_supported: bool
    reasons: list[str]

class Request(Strict):
    schema_version: Literal[1] = 1
    request_id: str = Field(min_length=1)
    lab: Literal['rca'] = 'rca'
    question: str = Field(min_length=1)
    mode: Literal['replay', 'live']
    snapshot_completed_at: str = Field(min_length=1)
    gate: Gate
    evidence: list[Reference] = Field(min_length=1)
    execution_allowed: Literal[False] = False

    @model_validator(mode='after')
    def unique_references(self):
        ids = [r.id for r in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate evidence IDs')
        if self.gate.decision == 'abstain' and self.gate.answer_supported:
            raise ValueError('Contradictory gate')
        return self

class Claim(Strict):
    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

class ProposedCommand(Strict):
    router: Literal['r1','r2','r3','r4','r5','r6']
    interface: str | None = None
    interpreter: Literal['linux_argv','vtysh_commands']
    arguments: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    validation_status: Literal['unvalidated'] = 'unvalidated'

class Response(Strict):
    schema_version: Literal[1] = 1
    request_id: str
    status: Literal['hypothesis', 'abstain']
    root_cause_hypothesis: str | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    claims: list[Claim]
    missing_evidence: list[str]
    proposed_patch: list[ProposedCommand]
    execution_allowed: Literal[False] = False

    @model_validator(mode='after')
    def check_abstention(self):
        if self.status == 'abstain' and (self.root_cause_hypothesis is not None or self.proposed_patch or self.confidence is not None):
            raise ValueError('Abstention cannot contain hypothesis, confidence or patch')
        if self.status == 'hypothesis' and (not self.root_cause_hypothesis or not self.claims):
            raise ValueError('Hypothesis requires statement and cited claims')
        return self

def validate_pair(request, response):
    req, res = Request.model_validate(request), Response.model_validate(response)
    if req.request_id != res.request_id:
        raise ValueError('Request ID mismatch')
    if (req.gate.decision != 'context_ready' or not req.gate.answer_supported) and res.status != 'abstain':
        raise ValueError('Gate requires abstention')
    ids = {e.id for e in req.evidence}
    for claim in [*res.claims, *res.proposed_patch]:
        if not set(claim.evidence_ids) <= ids:
            raise ValueError('Unknown evidence reference')
    return res
