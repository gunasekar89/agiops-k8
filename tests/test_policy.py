import pytest

from holmes_console.models import (
    ContainerEvidence,
    KubernetesEvidence,
    ValidationResult,
    ValidationStatus,
    WorkloadContext,
)
from holmes_console.policy import SafetyPolicy


def _safe_inputs():
    evidence = KubernetesEvidence(
        pod="web-abc",
        namespace="staging",
        phase="Unknown",
        owner="ReplicaSet/web-123",
        containers=[ContainerEvidence(waiting_reason="ContainerStatusUnknown")],
    )
    validation = ValidationResult(ValidationStatus.CONFIRMED)
    workload = WorkloadContext(
        kind="Deployment",
        name="web",
        desired_replicas=3,
        ready_replicas=2,
        available_replicas=2,
        selector="app=web",
    )
    return evidence, validation, workload


def test_low_risk_stale_deployment_pod_is_allowlisted():
    plan = SafetyPolicy().plan(*_safe_inputs())
    assert plan.allowed
    assert plan.action == "recycle_pod"
    assert plan.risk.safe
    assert plan.risk.score == 10


def test_unconfirmed_diagnosis_is_blocked():
    evidence, _, workload = _safe_inputs()
    plan = SafetyPolicy().plan(evidence, ValidationResult(ValidationStatus.PARTIAL), workload)
    assert not plan.allowed
    assert plan.risk.score == 100


def test_production_namespace_exceeds_safe_threshold():
    evidence, validation, workload = _safe_inputs()
    evidence.namespace = "production"
    plan = SafetyPolicy().plan(evidence, validation, workload)
    assert not plan.allowed
    assert plan.risk.score == 30


def test_common_failures_are_diagnosed_but_not_automatically_mutated():
    evidence, validation, workload = _safe_inputs()
    evidence.phase = "Running"
    evidence.containers[0].waiting_reason = "CrashLoopBackOff"
    plan = SafetyPolicy().plan(evidence, validation, workload)
    assert not plan.allowed
    assert plan.action == "none"


def test_risk_threshold_has_non_overridable_hard_cap():
    with pytest.raises(ValueError, match="hard safety cap"):
        SafetyPolicy(max_risk_score=26)
