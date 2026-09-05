"""Narrow, allowlisted Kubernetes remediation and recovery verification."""

import json
import shutil
import subprocess
import time

from .models import KubernetesEvidence, RemediationPlan, WorkloadContext
from .redaction import RedactionEngine


class RemediationError(RuntimeError):
    pass


class KubernetesRemediator:
    """Executes only code-defined actions; no LLM-produced command is accepted."""

    ALLOWED_ACTIONS = {"recycle_pod"}

    def __init__(self, executable: str = "kubectl", timeout: int = 180) -> None:
        self.executable = executable
        self.timeout = timeout
        self.redactor = RedactionEngine()

    def execute(
        self,
        plan: RemediationPlan,
        evidence: KubernetesEvidence,
        workload: WorkloadContext,
    ) -> str:
        if not plan.allowed or not plan.risk.safe:
            raise RemediationError("remediation blocked because the risk assessment is not safe")
        if plan.action not in self.ALLOWED_ACTIONS:
            raise RemediationError(f"action '{plan.action}' is not in the remediation allowlist")
        if plan.risk.threshold > 25:
            raise RemediationError("risk threshold exceeds the hard safety cap")
        if evidence.namespace in {
            "default",
            "holmes-system",
            "kube-system",
            "kube-public",
            "kube-node-lease",
        }:
            raise RemediationError("protected namespaces cannot be automatically remediated")
        if any(marker in evidence.namespace.lower() for marker in ("prod", "production", "live")):
            raise RemediationError("production-like namespaces require human escalation")
        if workload.kind != "Deployment" or not workload.name:
            raise RemediationError("only verified Deployment-managed pods may be recycled")
        if (
            workload.desired_replicas is None
            or workload.desired_replicas < 2
            or workload.available_replicas is None
            or workload.available_replicas < 1
        ):
            raise RemediationError("workload redundancy is no longer safe")
        if plan.target != f"pod/{evidence.pod}":
            raise RemediationError("remediation target does not match the investigated pod")

        self._preflight(evidence, workload)
        self._run(
            [
                "delete",
                "pod",
                evidence.pod,
                "-n",
                evidence.namespace,
                "--wait=true",
                "--timeout=60s",
            ]
        )
        self._wait_for_replacement(evidence, workload)
        return (
            f"Recycled {evidence.namespace}/{evidence.pod}; "
            f"deployment/{workload.name} reported a successful rollout."
        )

    def _run(self, args: list[str]) -> str:
        if shutil.which(self.executable) is None:
            raise RemediationError(f"kubectl executable '{self.executable}' was not found")
        try:
            result = subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout + 10,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemediationError("remediation verification timed out") from exc
        if result.returncode:
            safe_error = self.redactor.redact(result.stderr or result.stdout).strip()
            raise RemediationError(safe_error or "kubectl remediation command failed")
        return self.redactor.redact(result.stdout)

    def _wait_for_replacement(
        self, evidence: KubernetesEvidence, workload: WorkloadContext
    ) -> None:
        if workload.selector == "Not available":
            raise RemediationError("cannot verify recovery without a workload selector")
        deadline = time.monotonic() + self.timeout
        last_state = "replacement pod was not observed"
        while time.monotonic() < deadline:
            raw = self._run(
                [
                    "get",
                    "pods",
                    "-n",
                    evidence.namespace,
                    "-l",
                    workload.selector,
                    "-o",
                    "json",
                ]
            )
            try:
                pods = json.loads(raw).get("items", [])
            except (ValueError, AttributeError) as exc:
                raise RemediationError("kubectl returned malformed recovery evidence") from exc
            replacements = [
                pod for pod in pods if pod.get("metadata", {}).get("name") != evidence.pod
            ]
            ready = [
                pod
                for pod in replacements
                if any(
                    condition.get("type") == "Ready" and condition.get("status") == "True"
                    for condition in pod.get("status", {}).get("conditions", [])
                )
            ]
            desired = workload.desired_replicas or 1
            if len(ready) >= desired:
                return
            last_state = f"{len(ready)}/{desired} replacement workload pods are Ready"
            time.sleep(3)
        raise RemediationError(f"recovery verification failed: {last_state}")

    def _preflight(self, evidence: KubernetesEvidence, workload: WorkloadContext) -> None:
        """Re-read mutable state immediately before acting to prevent stale decisions."""
        raw_pod = self._run(["get", "pod", evidence.pod, "-n", evidence.namespace, "-o", "json"])
        raw_deployment = self._run(
            [
                "get",
                "deployment",
                workload.name,
                "-n",
                evidence.namespace,
                "-o",
                "json",
            ]
        )
        try:
            pod = json.loads(raw_pod)
            deployment = json.loads(raw_deployment)
        except (ValueError, AttributeError) as exc:
            raise RemediationError("kubectl returned malformed preflight evidence") from exc
        owners = pod.get("metadata", {}).get("ownerReferences") or []
        current_owner = f"{owners[0].get('kind', '')}/{owners[0].get('name', '')}" if owners else ""
        if current_owner != evidence.owner or not current_owner.startswith("ReplicaSet/"):
            raise RemediationError("pod ownership changed after investigation")
        status = pod.get("status", {})
        reasons = [
            ((item.get("state") or {}).get("waiting") or {}).get("reason", "")
            for item in status.get("containerStatuses") or []
        ]
        if status.get("phase") != "Unknown" and "ContainerStatusUnknown" not in reasons:
            raise RemediationError("stale-runtime condition cleared before remediation")
        desired = deployment.get("spec", {}).get("replicas", 0)
        available = deployment.get("status", {}).get("availableReplicas", 0)
        if desired < 2 or available < 1:
            raise RemediationError("deployment redundancy changed after risk assessment")
