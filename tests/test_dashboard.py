from io import StringIO

from rich.console import Console

from holmes_console.models import (
    ContainerEvidence,
    HolmesAnalysis,
    InvestigationResult,
    KubernetesEvidence,
    ValidationResult,
    ValidationStatus,
)
from holmes_console.ui.dashboard import Dashboard


def _render(width):
    stream = StringIO()
    console = Console(file=stream, width=width, color_system=None)
    dashboard = Dashboard(console)
    evidence = KubernetesEvidence(
        pod="web-app-abc",
        namespace="holmes-demo",
        phase="Running",
        node="worker-1",
        containers=[
            ContainerEvidence(name="web", waiting_reason="CrashLoopBackOff", restart_count=6)
        ],
        previous_logs="ERROR: connection refused",
    )
    result = InvestigationResult(
        evidence,
        HolmesAnalysis(
            root_cause="Database unavailable",
            evidence="Connection refused",
            recommended_actions="1. Check database",
            summary="Startup failure",
            structured=True,
        ),
        ValidationResult(ValidationStatus.CONFIRMED, ["connection refused"], "Supported"),
        18.4,
    )
    dashboard.show_context(evidence.pod, evidence.namespace)
    dashboard.render(result)
    return stream.getvalue()


def test_wide_terminal_contains_fixed_sections():
    output = _render(160)
    for label in ("ISSUE DETECTED", "KEY EVIDENCE", "ERROR DETAILS", "AI ANALYSIS", "SUMMARY"):
        assert label in output


def test_narrow_terminal_wraps_without_crashing():
    output = _render(72)
    assert "HolmesGPT" in output
    assert "CrashLoopBackOff" in output
