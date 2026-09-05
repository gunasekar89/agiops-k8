from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models import NOT_AVAILABLE, KubernetesEvidence


def issue_reason(evidence: KubernetesEvidence) -> str:
    container = evidence.primary_container
    for candidate in (container.waiting_reason, container.termination_reason, evidence.phase):
        if candidate and candidate != NOT_AVAILABLE:
            return candidate
    return NOT_AVAILABLE


def issue_panel(evidence: KubernetesEvidence) -> Panel:
    reason = issue_reason(evidence)
    body = Text()
    body.append(f"⚠ {reason}\n", style="bold yellow")
    body.append(_description(reason), style="white")
    return Panel(body, border_style="yellow", padding=(1, 2))


def evidence_panel(evidence: KubernetesEvidence) -> Panel:
    c = evidence.primary_container
    rows = (
        ("Pod", evidence.pod),
        ("Namespace", evidence.namespace),
        ("Status", evidence.phase),
        ("Reason", issue_reason(evidence)),
        ("Ready", evidence.ready),
        ("Restarts", str(sum(item.restart_count for item in evidence.containers))),
        ("Image", c.image),
        ("Node", evidence.node),
        ("Owner", evidence.owner),
        ("Exit code", str(c.exit_code) if c.exit_code is not None else NOT_AVAILABLE),
    )
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(style="bold cyan", width=14)
    table.add_column(style="white", overflow="fold")
    for label, value in rows:
        table.add_row(label, value)
    return Panel(table, title="2. KEY EVIDENCE", title_align="left", border_style="cyan")


def error_panel(evidence: KubernetesEvidence) -> Panel:
    log = evidence.previous_logs if evidence.previous_logs != NOT_AVAILABLE else evidence.logs
    return Panel(log, title="3. ERROR DETAILS", title_align="left", border_style="red")


def _description(reason: str) -> str:
    known = {
        "CrashLoopBackOff": "Container is repeatedly terminating and Kubernetes is restarting it.",
        "OOMKilled": "The container was terminated after exceeding its memory limit.",
        "ImagePullBackOff": "Kubernetes cannot pull the configured container image.",
        "Pending": "The pod has not been scheduled or started successfully.",
    }
    return known.get(reason, "Kubernetes reports an unhealthy workload state.")
