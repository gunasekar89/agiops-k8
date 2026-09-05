"""Alert-to-investigation-to-remediation orchestration."""

import re
import time
import uuid
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from threading import Lock
from typing import Any, Optional

from .analyzer import InvestigationAnalyzer
from .kubernetes import KubernetesCollector, KubernetesError
from .models import HealingMode, HealingReport, RemediationStatus, RiskAssessment
from .policy import SafetyPolicy
from .redaction import RedactionEngine
from .remediation import KubernetesRemediator, RemediationError


class AlertError(ValueError):
    pass


_KUBERNETES_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?$")


@dataclass(frozen=True)
class AlertTarget:
    namespace: str
    pod: str = ""
    deployment: str = ""
    fingerprint: str = ""
    auto_heal: bool = False


class AlertHealer:
    def __init__(
        self,
        analyzer: InvestigationAnalyzer,
        collector: KubernetesCollector,
        remediator: KubernetesRemediator,
        policy: SafetyPolicy,
        mode: HealingMode = HealingMode.OBSERVE,
        max_jobs: int = 1000,
    ) -> None:
        self.analyzer = analyzer
        self.collector = collector
        self.remediator = remediator
        self.policy = policy
        self.mode = mode
        self.max_jobs = max_jobs
        self.redactor = RedactionEngine()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._fingerprints: dict[str, str] = {}
        self._lock = Lock()

    def submit(self, alert: dict[str, Any], common_labels: dict[str, str]) -> tuple[str, bool]:
        target = parse_alert_target(alert, common_labels)
        with self._lock:
            self._prune_locked()
            if len(self._jobs) >= self.max_jobs:
                raise AlertError("healer job capacity reached; retry later")
            if target.fingerprint and target.fingerprint in self._fingerprints:
                return self._fingerprints[target.fingerprint], False
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = {
                "id": job_id,
                "status": "QUEUED",
                "mode": self.mode.value,
                "target": asdict(target),
                "created_at": time.time(),
            }
            if target.fingerprint:
                self._fingerprints[target.fingerprint] = job_id
        return job_id, True

    def process(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            target = AlertTarget(**job["target"])
            job["status"] = "INVESTIGATING"
        try:
            self.collector.check_connectivity()
            pod = target.pod
            if target.deployment:
                pod = self.collector.resolve_deployment_pod(target.namespace, target.deployment)
            elif not pod:
                unhealthy = self.collector.discover_unhealthy_pods(target.namespace)
                if not unhealthy:
                    raise KubernetesError(
                        f"No unhealthy pods found in namespace {target.namespace}"
                    )
                pod = unhealthy[0]
            investigation = self.analyzer.investigate(target.namespace, pod, lambda _label: None)
            workload = self.collector.workload_context(target.namespace, investigation.kubernetes)
            plan = self.policy.plan(investigation.kubernetes, investigation.validation, workload)
            if not plan.allowed:
                report = HealingReport(
                    investigation,
                    workload,
                    plan,
                    RemediationStatus.ESCALATED,
                    "Automatic remediation blocked by safety policy.",
                )
            elif self.mode is HealingMode.OBSERVE or not target.auto_heal:
                message = (
                    "Safe action identified; observe mode did not modify Kubernetes."
                    if self.mode is HealingMode.OBSERVE
                    else "Safe action identified, but alert is not explicitly labelled "
                    "auto_heal=true."
                )
                report = HealingReport(
                    investigation,
                    workload,
                    plan,
                    RemediationStatus.PROPOSED,
                    message,
                )
            else:
                try:
                    message = self.remediator.execute(plan, investigation.kubernetes, workload)
                    report = HealingReport(
                        investigation,
                        workload,
                        plan,
                        RemediationStatus.RECOVERED,
                        message,
                        "Not required; the replacement workload became Ready.",
                    )
                except RemediationError as exc:
                    report = HealingReport(
                        investigation,
                        workload,
                        plan,
                        RemediationStatus.ESCALATED,
                        f"Remediation or recovery verification failed: {exc}",
                        "Pod recreation is controller-managed and cannot be reversed; "
                        "further mutation was stopped and human escalation is required.",
                    )
            self._complete(job_id, report)
        except Exception as exc:  # noqa: BLE001 - job boundary must record failures safely
            self._fail(job_id, exc)

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            value = self._jobs.get(job_id)
            return dict(value) if value else None

    def _complete(self, job_id: str, report: HealingReport) -> None:
        with self._lock:
            self._jobs[job_id].update(
                {
                    "status": report.status.value,
                    "completed_at": time.time(),
                    "report": to_jsonable(self.redactor.redact_object(report)),
                }
            )

    def _fail(self, job_id: str, exc: Exception) -> None:
        with self._lock:
            self._jobs[job_id].update(
                {
                    "status": "ESCALATED",
                    "completed_at": time.time(),
                    "error": self.redactor.redact(str(exc)),
                }
            )

    def _prune_locked(self) -> None:
        if len(self._jobs) < self.max_jobs:
            return
        completed = sorted(
            (
                value
                for value in self._jobs.values()
                if value["status"] not in {"QUEUED", "INVESTIGATING"}
            ),
            key=lambda value: value["created_at"],
        )
        while len(self._jobs) >= self.max_jobs and completed:
            removed = completed.pop(0)
            self._jobs.pop(removed["id"], None)
            fingerprint = removed["target"].get("fingerprint")
            if fingerprint:
                self._fingerprints.pop(fingerprint, None)


def parse_alert_target(alert: dict[str, Any], common_labels: dict[str, str]) -> AlertTarget:
    if alert.get("status", "firing") != "firing":
        raise AlertError("resolved alerts do not trigger investigations")
    labels = {**common_labels, **(alert.get("labels") or {})}
    namespace = labels.get("namespace") or labels.get("kubernetes_namespace") or ""
    pod = labels.get("pod") or labels.get("pod_name") or labels.get("kubernetes_pod_name") or ""
    deployment = labels.get("deployment") or labels.get("deployment_name") or ""
    if not namespace:
        raise AlertError("alert requires a namespace label")
    for label, value in (("namespace", namespace), ("pod", pod), ("deployment", deployment)):
        if value and not _KUBERNETES_NAME.fullmatch(value):
            raise AlertError(f"alert contains an invalid Kubernetes {label} name")
    return AlertTarget(
        namespace=namespace,
        pod=pod,
        deployment=deployment,
        fingerprint=str(alert.get("fingerprint") or ""),
        auto_heal=str(labels.get("auto_heal") or "").lower() == "true",
    )


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, RiskAssessment):
        return {
            "score": value.score,
            "threshold": value.threshold,
            "safe": value.safe,
            "factors": to_jsonable(value.factors),
        }
    if is_dataclass(value):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
