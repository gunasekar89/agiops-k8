import json
from unittest.mock import Mock, patch

import pytest

from holmes_console.models import (
    KubernetesEvidence,
    RemediationPlan,
    RiskAssessment,
    WorkloadContext,
)
from holmes_console.remediation import KubernetesRemediator, RemediationError


def _plan(allowed=True):
    return RemediationPlan(
        "recycle_pod",
        "pod/web-old",
        "stale runtime",
        RiskAssessment(10 if allowed else 100, 25),
        allowed,
    )


def _target():
    evidence = KubernetesEvidence("web-old", "staging", owner="ReplicaSet/web-rs")
    workload = WorkloadContext("Deployment", "web", 2, 1, 1, "app=web")
    return evidence, workload


def test_blocked_plan_never_invokes_kubectl():
    remediator = KubernetesRemediator()
    evidence, workload = _target()
    with patch("subprocess.run") as run, pytest.raises(RemediationError, match="blocked"):
        remediator.execute(_plan(False), evidence, workload)
    run.assert_not_called()


def test_executes_exact_allowlisted_delete_and_verifies_replacement():
    pod = {
        "metadata": {
            "name": "web-old",
            "ownerReferences": [{"kind": "ReplicaSet", "name": "web-rs"}],
        },
        "status": {
            "phase": "Unknown",
            "containerStatuses": [],
        },
    }
    deployment = {
        "spec": {"replicas": 2},
        "status": {"availableReplicas": 1},
    }
    replacement = {
        "items": [
            {
                "metadata": {"name": name},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }
            for name in ("web-peer", "web-new")
        ]
    }
    responses = [
        Mock(returncode=0, stdout=json.dumps(pod), stderr=""),
        Mock(returncode=0, stdout=json.dumps(deployment), stderr=""),
        Mock(returncode=0, stdout="pod deleted", stderr=""),
        Mock(returncode=0, stdout=json.dumps(replacement), stderr=""),
    ]
    evidence, workload = _target()
    with (
        patch("shutil.which", return_value="/usr/bin/kubectl"),
        patch("subprocess.run", side_effect=responses) as run,
    ):
        message = KubernetesRemediator().execute(_plan(), evidence, workload)
    assert run.call_args_list[2].args[0][:4] == [
        "kubectl",
        "delete",
        "pod",
        "web-old",
    ]
    assert "successful" in message


def test_preflight_blocks_if_stale_condition_has_cleared():
    healthy_pod = {
        "metadata": {
            "ownerReferences": [{"kind": "ReplicaSet", "name": "web-rs"}],
        },
        "status": {"phase": "Running", "containerStatuses": []},
    }
    deployment = {"spec": {"replicas": 2}, "status": {"availableReplicas": 1}}
    responses = [
        Mock(returncode=0, stdout=json.dumps(healthy_pod), stderr=""),
        Mock(returncode=0, stdout=json.dumps(deployment), stderr=""),
    ]
    evidence, workload = _target()
    evidence.owner = "ReplicaSet/web-rs"
    with (
        patch("shutil.which", return_value="/usr/bin/kubectl"),
        patch("subprocess.run", side_effect=responses) as run,
        pytest.raises(RemediationError, match="condition cleared"),
    ):
        KubernetesRemediator().execute(_plan(), evidence, workload)
    assert run.call_count == 2


def test_rejects_non_allowlisted_action():
    plan = _plan()
    plan.action = "apply_holmes_command"
    evidence, workload = _target()
    with pytest.raises(RemediationError, match="allowlist"):
        KubernetesRemediator().execute(plan, evidence, workload)
