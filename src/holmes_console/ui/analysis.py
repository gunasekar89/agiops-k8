from rich.panel import Panel
from rich.text import Text

from ..models import HolmesAnalysis, ValidationResult


def analysis_panel(analysis: HolmesAnalysis, validation: ValidationResult) -> Panel:
    body = Text()
    if not analysis.structured:
        body.append("AI INVESTIGATION OUTPUT\n\n", style="bold magenta")
        body.append(analysis.raw_output or "Not available")
    else:
        for heading, value in (
            ("ROOT CAUSE", analysis.root_cause),
            ("EVIDENCE", analysis.evidence),
            ("RECOMMENDED ACTIONS", analysis.recommended_actions),
        ):
            body.append(f"{heading}\n", style="bold magenta")
            body.append(f"{value}\n\n", style="white")
    color = {"CONFIRMED": "green", "PARTIAL": "yellow", "UNVERIFIED": "red"}[
        validation.status.value
    ]
    body.append("EVIDENCE VALIDATION  ", style="bold white")
    body.append(validation.status.value, style=f"bold {color}")
    body.append(f"\n{validation.explanation}", style="dim")
    if validation.matched_terms:
        body.append("\nMatched: " + ", ".join(validation.matched_terms), style="dim green")
    return Panel(
        body, title="4. AI ANALYSIS", title_align="left", border_style="magenta", padding=(1, 2)
    )
