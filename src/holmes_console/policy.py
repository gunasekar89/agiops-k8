"""Deterministic safety policy and risk scoring for autonomous remediation."""

from dataclasses import dataclass, field

from .models import (
    KubernetesEvidence,
    RemediationPlan,
    RiskAssessment,
    ValidationResult,
    ValidationStatus,
    WorkloadContext,
)


@dataclass(frozen=True)
class SafetyPolicy:
    """Hard safety bounds; HolmesGPT text can never override these controls."""

    max_risk_score: int = 25
    protected_namespaces: set[str] = field(
        default_factory=lambda: {
            "default",
            "holmes-system",
            "kube-system",
            "kube-public",
            "kube-node-lease",
        }
    )
    production_markers: tuple[str, ...] = ("prod", "production", "live")

    def __post_init__(self) -> None:
        if not 0 <= self.max_risk_score <= 25:
            raise ValueError("max_risk_score must remain between 0 and the hard safety cap of 25")

    def plan(
        self,
        evidence: KubernetesEvidence,
        validation: ValidationResult,
        workload: WorkloadContext,
    ) -> RemediationPlan:
        factors: list[str] = []
        score = 10

        if validation.status is not ValidationStatus.CONFIRMED:
            score += 100
            factors.append("HolmesGPT diagnosis is not independently CONFIRMED (+100)")
        if evidence.namespace in self.protected_namespaces:
            score += 100
            factors.append("target is in a protected Kubernetes namespace (+100)")
        if any(marker in evidence.namespace.lower() for marker in self.production_markers):
            score += 20
            factors.append("namespace appears production-critical (+20)")
        if workload.kind != "Deployment" or workload.name == "Not available":
            score += 100
            factors.append("pod is not backed by a verified Deployment (+100)")
        if workload.desired_replicas is None or workload.available_replicas is None:
            score += 50
            factors.append("workload redundancy could not be verified (+50)")
        elif workload.desired_replicas < 2 or workload.available_replicas < 1:
            score += 50
            factors.append("workload does not have a verified available peer (+50)")
        if len(evidence.containers) > 1:
            score += 10
            factors.append("pod has multiple containers (+10)")

        corpus = " ".join(
            [
                evidence.phase,
                evidence.describe,
                *[
                    f"{item.waiting_reason} {item.termination_reason}"
                    for item in evidence.containers
                ],
                *[f"{item.reason} {item.message}" for item in evidence.events],
            ]
        ).lower()
        stale_signals = ("containerstatusunknown", "node lost", "nodelost", "pod unknown")
        if not any(signal in corpus for signal in stale_signals):
            score += 100
            factors.append("no independently observed stale-runtime signal (+100)")

        risk = RiskAssessment(min(score, 100), self.max_risk_score, factors)
        allowed = risk.safe
        reason = (
            "Recycle one stale Deployment-managed pod and let its controller create a replacement."
            if allowed
            else "No allowlisted remediation satisfies the safety policy; escalate for review."
        )
        return RemediationPlan(
            action="recycle_pod" if allowed else "none",
            target=f"pod/{evidence.pod}",
            reason=reason,
            risk=risk,
            allowed=allowed,
        )
