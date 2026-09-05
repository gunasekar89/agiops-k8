import json
from pathlib import Path
from unittest.mock import patch

import pytest

from holmes_console.kubernetes import KubernetesCollector, KubernetesError
from holmes_console.models import KubernetesEvidence

FIXTURE = Path(__file__).parent / "fixtures" / "pod.json"


def test_extracts_pod_evidence():
    collector = KubernetesCollector()
    data = json.loads(FIXTURE.read_text())
    evidence = collector._from_pod(data, "holmes-demo", "web-app-abc")
    assert evidence.phase == "Running"
    assert evidence.primary_container.waiting_reason == "CrashLoopBackOff"
    assert evidence.primary_container.restart_count == 6
    assert evidence.primary_container.exit_code == 1


def test_unhealthy_detection():
    data = json.loads(FIXTURE.read_text())
    assert KubernetesCollector._is_unhealthy(data)


def test_missing_kubectl_has_actionable_error():
    collector = KubernetesCollector("definitely-missing-kubectl")
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(KubernetesError, match="not found"),
    ):
        collector.check_connectivity()


def test_no_logs_are_reported_as_not_available():
    collector = KubernetesCollector()
    data = json.loads(FIXTURE.read_text())
    responses = [json.dumps(data), "pod description", '{"items": []}', "", ""]
    with patch.object(collector, "_run", side_effect=responses):
        evidence = collector.collect("holmes-demo", "web-app-abc")
    assert evidence.logs == "Not available"
    assert evidence.previous_logs == "Not available"


def test_resolves_replicaset_to_redundant_deployment_context():
    collector = KubernetesCollector()
    replica_set = {"metadata": {"ownerReferences": [{"kind": "Deployment", "name": "web"}]}}
    deployment = {
        "spec": {"replicas": 3, "selector": {"matchLabels": {"app": "web"}}},
        "status": {"readyReplicas": 2, "availableReplicas": 2},
    }
    evidence = KubernetesEvidence(pod="web-old", namespace="staging", owner="ReplicaSet/web-rs")
    with patch.object(
        collector, "_run", side_effect=[json.dumps(replica_set), json.dumps(deployment)]
    ):
        workload = collector.workload_context("staging", evidence)
    assert workload.kind == "Deployment"
    assert workload.name == "web"
    assert workload.desired_replicas == 3
    assert workload.available_replicas == 2
    assert workload.selector == "app=web"
