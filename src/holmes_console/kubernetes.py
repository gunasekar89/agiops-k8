"""Read-only Kubernetes evidence collection via the stable kubectl interface."""

import json
import shutil
import subprocess
from typing import Any

from .models import NOT_AVAILABLE, ContainerEvidence, EventEvidence, KubernetesEvidence
from .redaction import RedactionEngine


class KubernetesError(RuntimeError):
    pass


class KubernetesCollector:
    def __init__(self, executable: str = "kubectl", timeout: int = 45, max_log_chars: int = 24_000):
        self.executable = executable
        self.timeout = timeout
        self.max_log_chars = max_log_chars
        self.redactor = RedactionEngine()

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _run(self, args: list[str], allow_failure: bool = False) -> str:
        if not self.available():
            raise KubernetesError(
                f"kubectl executable '{self.executable}' was not found. Install kubectl and "
                "ensure it is on PATH."
            )
        try:
            result = subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise KubernetesError(f"kubectl timed out after {self.timeout} seconds") from exc
        stdout = self.redactor.redact(result.stdout)
        stderr = self.redactor.redact(result.stderr)
        if result.returncode and not allow_failure:
            raise KubernetesError(stderr.strip() or stdout.strip() or "kubectl command failed")
        return stdout if result.returncode == 0 else ""

    def check_connectivity(self) -> None:
        self._run(["cluster-info", "--request-timeout=10s"])

    def discover_unhealthy_pods(self, namespace: str, deployment: str = "") -> list[str]:
        args = ["get", "pods", "-n", namespace, "-o", "json"]
        payload = self._json(self._run(args), "pod list")
        pods = []
        for pod in payload.get("items", []):
            if deployment and not self._belongs_to(pod, deployment):
                continue
            if self._is_unhealthy(pod):
                pods.append(pod.get("metadata", {}).get("name", ""))
        return [name for name in pods if name]

    def resolve_deployment_pod(self, namespace: str, deployment: str) -> str:
        deployment_json = self._json(
            self._run(["get", "deployment", deployment, "-n", namespace, "-o", "json"]),
            "deployment",
        )
        labels = deployment_json.get("spec", {}).get("selector", {}).get("matchLabels", {})
        if not labels:
            raise KubernetesError(
                f"Deployment {namespace}/{deployment} has no matchLabels selector"
            )
        selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        payload = self._json(
            self._run(["get", "pods", "-n", namespace, "-l", selector, "-o", "json"]),
            "deployment pods",
        )
        items = payload.get("items", [])
        if not items:
            raise KubernetesError(f"No pods found for deployment {namespace}/{deployment}")
        unhealthy = [pod for pod in items if self._is_unhealthy(pod)]
        chosen = (unhealthy or items)[0]
        return chosen.get("metadata", {}).get("name", "")

    def collect(self, namespace: str, pod: str) -> KubernetesEvidence:
        raw = self._run(["get", "pod", pod, "-n", namespace, "-o", "json"])
        data = self._json(raw, "pod")
        evidence = self._from_pod(data, namespace, pod)
        evidence.describe = (
            self._run(["describe", "pod", pod, "-n", namespace], allow_failure=True).strip()
            or NOT_AVAILABLE
        )
        evidence.events = self._collect_events(namespace, pod)
        logs, previous = [], []
        names = [item.name for item in evidence.containers if item.name != NOT_AVAILABLE]
        for container in names:
            current = self._run(
                ["logs", pod, "-n", namespace, "-c", container, "--tail=250"],
                allow_failure=True,
            ).strip()
            old = self._run(
                ["logs", pod, "-n", namespace, "-c", container, "--previous", "--tail=250"],
                allow_failure=True,
            ).strip()
            if current:
                logs.append(f"[{container}]\n{current}")
            if old:
                previous.append(f"[{container}]\n{old}")
        evidence.logs = self._bounded("\n\n".join(logs))
        evidence.previous_logs = self._bounded("\n\n".join(previous))
        return evidence

    def _collect_events(self, namespace: str, pod: str) -> list[EventEvidence]:
        raw = self._run(
            [
                "get",
                "events",
                "-n",
                namespace,
                "--field-selector",
                f"involvedObject.name={pod}",
                "-o",
                "json",
            ],
            allow_failure=True,
        )
        if not raw:
            return []
        payload = self._json(raw, "events")
        events = []
        for item in payload.get("items", []):
            events.append(
                EventEvidence(
                    event_type=item.get("type") or NOT_AVAILABLE,
                    reason=item.get("reason") or NOT_AVAILABLE,
                    message=item.get("message") or NOT_AVAILABLE,
                    count=item.get("count") or 0,
                    last_timestamp=(
                        item.get("lastTimestamp") or item.get("eventTime") or NOT_AVAILABLE
                    ),
                )
            )
        return events[-20:]

    def _from_pod(self, data: dict[str, Any], namespace: str, pod: str) -> KubernetesEvidence:
        metadata, spec, status = (
            data.get("metadata", {}),
            data.get("spec", {}),
            data.get("status", {}),
        )
        owners = metadata.get("ownerReferences") or []
        owner = (
            f"{owners[0].get('kind', NOT_AVAILABLE)}/{owners[0].get('name', NOT_AVAILABLE)}"
            if owners
            else NOT_AVAILABLE
        )
        specs = {item.get("name"): item for item in spec.get("containers", [])}
        statuses = status.get("containerStatuses") or []
        containers = []
        for item in statuses:
            state_data = item.get("state") or {}
            state = next(
                (
                    key
                    for key in ("waiting", "running", "terminated")
                    if state_data.get(key) is not None
                ),
                NOT_AVAILABLE,
            )
            waiting = state_data.get("waiting") or {}
            terminated = state_data.get("terminated") or {}
            last_terminated = (item.get("lastState") or {}).get("terminated") or {}
            containers.append(
                ContainerEvidence(
                    name=item.get("name") or NOT_AVAILABLE,
                    image=item.get("image")
                    or specs.get(item.get("name"), {}).get("image")
                    or NOT_AVAILABLE,
                    ready=item.get("ready"),
                    restart_count=item.get("restartCount") or 0,
                    state=state,
                    waiting_reason=waiting.get("reason") or NOT_AVAILABLE,
                    termination_reason=terminated.get("reason")
                    or last_terminated.get("reason")
                    or NOT_AVAILABLE,
                    exit_code=terminated.get("exitCode", last_terminated.get("exitCode")),
                )
            )
        if not containers:
            containers = [
                ContainerEvidence(
                    name=name or NOT_AVAILABLE, image=value.get("image") or NOT_AVAILABLE
                )
                for name, value in specs.items()
            ]
        ready_condition = next(
            (c.get("status") for c in status.get("conditions", []) if c.get("type") == "Ready"),
            None,
        )
        return KubernetesEvidence(
            pod=metadata.get("name") or pod,
            namespace=metadata.get("namespace") or namespace,
            phase=status.get("phase") or NOT_AVAILABLE,
            node=spec.get("nodeName") or NOT_AVAILABLE,
            owner=owner,
            ready=ready_condition or NOT_AVAILABLE,
            containers=containers,
        )

    @staticmethod
    def _is_unhealthy(pod: dict[str, Any]) -> bool:
        status = pod.get("status", {})
        if status.get("phase") in {"Failed", "Unknown", "Pending"}:
            return True
        for container in status.get("containerStatuses") or []:
            waiting = (container.get("state") or {}).get("waiting") or {}
            if waiting.get("reason"):
                return True
            if not container.get("ready", False) or (container.get("restartCount") or 0) > 0:
                return True
        return False

    @staticmethod
    def _belongs_to(pod: dict[str, Any], deployment: str) -> bool:
        return any(
            deployment in owner.get("name", "")
            for owner in pod.get("metadata", {}).get("ownerReferences") or []
        )

    @staticmethod
    def _json(value: str, label: str) -> dict[str, Any]:
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise KubernetesError(f"kubectl returned malformed JSON for {label}") from exc

    def _bounded(self, value: str) -> str:
        if not value:
            return NOT_AVAILABLE
        if len(value) <= self.max_log_chars:
            return value
        return "[...truncated...]\n" + value[-self.max_log_chars :]
