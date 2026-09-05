"""Typed domain models shared by collectors, analysis, and presentation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

NOT_AVAILABLE = "Not available"


class ValidationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class ContainerEvidence:
    name: str = NOT_AVAILABLE
    image: str = NOT_AVAILABLE
    ready: Optional[bool] = None
    restart_count: int = 0
    state: str = NOT_AVAILABLE
    waiting_reason: str = NOT_AVAILABLE
    termination_reason: str = NOT_AVAILABLE
    exit_code: Optional[int] = None


@dataclass
class EventEvidence:
    event_type: str = NOT_AVAILABLE
    reason: str = NOT_AVAILABLE
    message: str = NOT_AVAILABLE
    count: int = 0
    last_timestamp: str = NOT_AVAILABLE


@dataclass
class KubernetesEvidence:
    pod: str
    namespace: str
    phase: str = NOT_AVAILABLE
    node: str = NOT_AVAILABLE
    owner: str = NOT_AVAILABLE
    ready: str = NOT_AVAILABLE
    containers: list[ContainerEvidence] = field(default_factory=list)
    events: list[EventEvidence] = field(default_factory=list)
    logs: str = NOT_AVAILABLE
    previous_logs: str = NOT_AVAILABLE
    describe: str = NOT_AVAILABLE

    @property
    def primary_container(self) -> ContainerEvidence:
        return self.containers[0] if self.containers else ContainerEvidence()


@dataclass
class HolmesAnalysis:
    root_cause: str = NOT_AVAILABLE
    evidence: str = NOT_AVAILABLE
    recommended_actions: str = NOT_AVAILABLE
    summary: str = NOT_AVAILABLE
    raw_output: str = ""
    structured: bool = False


@dataclass
class ValidationResult:
    status: ValidationStatus
    matched_terms: list[str] = field(default_factory=list)
    explanation: str = NOT_AVAILABLE


@dataclass
class InvestigationResult:
    kubernetes: KubernetesEvidence
    analysis: HolmesAnalysis
    validation: ValidationResult
    elapsed_seconds: float
