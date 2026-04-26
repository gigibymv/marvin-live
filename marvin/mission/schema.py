from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Confidence = Literal["KNOWN", "REASONED", "LOW_CONFIDENCE"]
HypothesisStatus = Literal["active", "validated", "invalidated", "abandoned"]
WorkstreamStatus = Literal["pending", "in_progress", "delivered"]
MilestoneStatus = Literal["pending", "in_progress", "delivered", "skipped"]
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


class Hypothesis(MarvinModel):
    id: str
    mission_id: str
    text: str
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
    hypothesis_id: str | None = None
    claim_text: str
    confidence: Confidence
    source_id: str | None = None
    agent_id: str | None = None
    human_validated: bool = False
    created_at: str | None = None

    @model_validator(mode="after")
    def validate_known_source(self) -> "Finding":
        if self.confidence == "KNOWN" and not self.source_id:
            raise ValueError("source_id required for KNOWN findings")
        return self


class Source(MarvinModel):
    id: str
    mission_id: str
    url_or_ref: str | None = None
    quote: str | None = None
    retrieved_at: str | None = None


class Gate(MarvinModel):
    id: str
    mission_id: str
    gate_type: str
    scheduled_day: int
    validator_role: str = "manager"
    status: GateStatus = "pending"
    completion_notes: str | None = None
    format: str | None = None


class Deliverable(MarvinModel):
    id: str
    mission_id: str
    deliverable_type: str
    status: str = "pending"
    file_path: str | None = None
    file_size_bytes: int | None = None
    created_at: str | None = None

    @field_validator("file_path")
    @classmethod
    def validate_absolute_file_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not Path(value).is_absolute():
            raise ValueError("file_path must be absolute")
        return value


class MerlinVerdict(MarvinModel):
    id: str
    mission_id: str
    verdict: MerlinVerdictValue
    gate_id: str | None = None
    notes: str | None = None
    created_at: str | None = None
