from unittest.mock import Mock

import pytest

from holmes_console.healer import AlertError, AlertHealer, parse_alert_target
from holmes_console.models import (
    ContainerEvidence,
    HealingMode,
    HolmesAnalysis,
    InvestigationResult,
    KubernetesEvidence,
    ValidationResult,
    ValidationStatus,
    WorkloadContext,
)
from holmes_console.policy import SafetyPolicy


def _investigation():
    evidence = KubernetesEvidence(
        "web-old",
        "staging",
        phase="Unknown",
        owner="ReplicaSet/web-rs",
        containers=[ContainerEvidence(waiting_reason="ContainerStatusUnknown")],
    )
    return InvestigationResult(
        evidence,
        HolmesAnalysis(root_cause="ContainerStatusUnknown"),
        ValidationResult(ValidationStatus.CONFIRMED),
        1.0,
    )


def test_alert_target_accepts_prometheus_kubernetes_labels():
    target = parse_alert_target(
        {"status": "firing", "labels": {"pod": "web-abc"}, "fingerprint": "fp1"},
        {"namespace": "staging"},
    )
    assert target.namespace == "staging"
    assert target.pod == "web-abc"


def test_resolved_alert_is_rejected():
    with pytest.raises(AlertError, match="resolved"):
        parse_alert_target({"status": "resolved"}, {"namespace": "staging"})


def test_automatic_mode_executes_only_safe_plan():
    analyzer = Mock()
    analyzer.investigate.return_value = _investigation()
    collector = Mock()
    collector.workload_context.return_value = WorkloadContext(
        "Deployment", "web", 3, 2, 2, "app=web"
    )
    remediator = Mock()
    remediator.execute.return_value = "recovered"
    healer = AlertHealer(analyzer, collector, remediator, SafetyPolicy(), HealingMode.AUTOMATIC)
    job_id, created = healer.submit(
        {
            "status": "firing",
            "labels": {
                "namespace": "staging",
                "pod": "web-old",
                "auto_heal": "true",
            },
        },
        {},
    )
    assert created
    healer.process(job_id)
    job = healer.get(job_id)
    assert job["status"] == "RECOVERED"
    assert job["report"]["plan"]["risk"]["safe"] is True
    remediator.execute.assert_called_once()


def test_automatic_mode_requires_explicit_alert_opt_in():
    analyzer = Mock()
    analyzer.investigate.return_value = _investigation()
    collector = Mock()
    collector.workload_context.return_value = WorkloadContext(
        "Deployment", "web", 3, 2, 2, "app=web"
    )
    remediator = Mock()
    healer = AlertHealer(analyzer, collector, remediator, SafetyPolicy(), HealingMode.AUTOMATIC)
    job_id, _ = healer.submit(
        {"status": "firing", "labels": {"namespace": "staging", "pod": "web-old"}},
        {},
    )
    healer.process(job_id)
    assert healer.get(job_id)["status"] == "PROPOSED"
    remediator.execute.assert_not_called()


def test_fingerprint_deduplicates_alert_retries():
    healer = AlertHealer(Mock(), Mock(), Mock(), SafetyPolicy())
    alert = {
        "status": "firing",
        "fingerprint": "same",
        "labels": {"namespace": "staging", "pod": "web-old"},
    }
    first, created_first = healer.submit(alert, {})
    second, created_second = healer.submit(alert, {})
    assert (first, True) == (second, created_first)
    assert not created_second
