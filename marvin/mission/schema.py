from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Confidence = Literal["KNOWN", "REASONED", "LOW_CONFIDENCE"]
FindingImpact = Literal["load_bearing", "supporting", "color"]
HypothesisStatus = Literal["active", "validated", "invalidated", "abandoned"]
WorkstreamStatus = Literal["pending", "in_progress", "delivered"]
MilestoneStatus = Literal["pending", "in_progress", "delivered", "skipped", "blocked"]
GateStatus = Literal["pending", "completed", "failed"]
MerlinVerdictValue = Literal["SHIP", "MINOR_FIXES", "BACK_TO_DRAWING_BOARD"]


class MarvinModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mission(MarvinModel):
    id: str
    client: str
    target: str
    mission_type: str = "cdd"
    ic_question: str | None = None
    status: str = "active"
    active_agent: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    clarification_rounds_used: int = 0
    clarification_answers: list[str] = Field(default_factory=list)
    data_room_path: str | None = None  # Bug 3 (chantier 2.6): user-provided primary data room


class MissionBrief(MarvinModel):
    mission_id: str
    raw_brief: str
    ic_question: str
    mission_angle: str
    brief_summary: str
    workstream_plan_json: str
    created_at: str | None = None
    updated_at: str | None = None


class Hypothesis(MarvinModel):
    id: str
    mission_id: str
    text: str
    label: str | None = None  # H1, H2, ... — user-facing reference (Bug 4)
    status: HypothesisStatus = "active"
    abandon_reason: str | None = None
    created_at: str | None = None


class Workstream(MarvinModel):
    id: str
    mission_id: str
    label: str
    assigned_agent: str | None = None
    status: WorkstreamStatus = "pending"


class Milestone(MarvinModel):
    id: str
    mission_id: str
    workstream_id: str
    label: str
    status: MilestoneStatus = "pending"
    result_summary: str | None = None
    scheduled_day: int | None = None


class Finding(MarvinModel):
    id: str
    mission_id: str
    workstream_id: str | None = None
    milestone_id: str | None = None  # C-PER-MILESTONE: tag findings to a milestone for per-milestone reports
    hypothesis_id: str | None = None
    claim_text: str
    confidence: Confidence
    source_id: str | None = None
    agent_id: str | None = None
    human_validated: bool = False
    created_at: str | None = None
    impact: FindingImpact | None = None  # Chantier 4: load_bearing | supporting | color
    source_type: str | None = None  # sec_filing | web | data_room | inference | press
    corroboration_count: int = 1  # C4: number of independent sources
    corroboration_status: str | None = None  # 'corroborated' | 'single_source' | 'downgraded'

    @model_validator(mode="after")
    def validate_known_source(self) -> "Finding":
        if self.confidence == "KNOWN" and not self.source_id:
            raise ValueError("source_id required for KNOWN findings")
        return self

    @model_validator(mode="after")
    def validate_load_bearing_confidence(self) -> "Finding":
        # Chantier 4: load_bearing findings must be KNOWN or REASONED, not LOW.
        if self.impact == "load_bearing" and self.confidence == "LOW_CONFIDENCE":
            raise ValueError("load_bearing findings cannot be LOW_CONFIDENCE")
        return self


class Source(MarvinModel):
    id: str
    mission_id: str
    url_or_ref: str | None = None
    quote: str | None = None
    retrieved_at: str | None = None
    source_type: str | None = None  # sec_filing | web | data_room | transcript | inference | press


class Gate(MarvinModel):
    id: str
    mission_id: str
    gate_type: str
    scheduled_day: int
    validator_role: str = "manager"
    status: GateStatus = "pending"
    completion_notes: str | None = None
    format: str | None = None
    questions: list[str] | None = None
    # C-RESUME-RECOVERY: structured cause for status="failed" gates so the UI
    # can render a precise "Adversus failed — OpenRouter unavailable" card and
    # offer a targeted Rerun button. Shape: {agent, error, cause, retries_exhausted}.
    failure_reason: dict | None = None
    opened_at: str | None = None
    closed_at: str | None = None


class Deliverable(MarvinModel):
    id: str
    mission_id: str
    deliverable_type: str
    status: str = "pending"
    file_path: str | None = None
    file_size_bytes: int | None = None
    created_at: str | None = None
    milestone_id: str | None = None  # C-PER-MILESTONE: pair a deliverable with a milestone row in the UI
    workstream_id: str | None = None  # tab routing: W1/W2/W4 for workstream+milestone reports, null for global

    @field_validator("file_path")
    @classmethod
    def validate_absolute_file_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not Path(value).is_absolute():
            raise ValueError("file_path must be absolute")
        return value


class DataRoomFile(MarvinModel):
    id: str
    mission_id: str
    filename: str
    file_path: str
    mime_type: str | None = None
    size_bytes: int | None = None
    parsed_text: str | None = None
    parse_error: str | None = None
    uploaded_at: str | None = None


class Transcript(MarvinModel):
    id: str
    mission_id: str
    title: str | None = None
    expert_name: str | None = None
    expert_role: str | None = None
    raw_text: str
    line_count: int | None = None
    uploaded_at: str | None = None


class TranscriptSegment(MarvinModel):
    id: str
    transcript_id: str
    speaker: str | None = None
    text: str
    line_start: int | None = None
    line_end: int | None = None


class DealTerms(MarvinModel):
    """Deal economics captured by the deal team at mission start.

    All monetary values in millions. Multiples are expressed as floats
    (e.g. 12.5x = 12.5). target_irr / target_moic / leverage_x and
    multiples are dimensionless. None means "not provided yet" — every
    field is optional so partial captures are valid.
    """

    mission_id: str
    entry_revenue: float | None = None
    entry_ebitda: float | None = None
    entry_multiple: float | None = None
    entry_equity: float | None = None
    leverage_x: float | None = None
    hold_years: int | None = None
    target_irr: float | None = None
    target_moic: float | None = None
    sector_multiple_low: float | None = None
    sector_multiple_high: float | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MerlinVerdict(MarvinModel):
    id: str
    mission_id: str
    verdict: MerlinVerdictValue
    gate_id: str | None = None
    notes: str | None = None
    created_at: str | None = None
