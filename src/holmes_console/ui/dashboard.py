import shutil

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from ..models import InvestigationResult
from .analysis import analysis_panel
from .evidence import error_panel, evidence_panel, issue_panel
from .header import build_header
from .summary import summary_panel


class Dashboard:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.completed = []

    def show_context(self, pod: str, namespace: str) -> None:
        self.console.print(build_header())
        self.console.print()
        self.console.print(Text.assemble("Investigating issue for pod: ", (pod, "bold white")))
        self.console.print(Text.assemble("Namespace: ", (namespace, "bold cyan")))
        self.console.print()

    def step_succeeded(self, label: str) -> None:
        self.completed.append(label)
        self.console.print(Text.assemble(("✓ ", "bold green"), label))

    def render(self, result: InvestigationResult) -> None:
        self.console.print()
        self.console.print(Rule("1. ISSUE DETECTED", style="yellow"))
        self.console.print(issue_panel(result.kubernetes))
        self.console.print(evidence_panel(result.kubernetes))
        self.console.print(error_panel(result.kubernetes))
        self.console.print(analysis_panel(result.analysis, result.validation))
        self.console.print(Rule("5. SUMMARY", style="green"))
        self.console.print(summary_panel(result.analysis))
        self.console.print()
        self.console.print(
            f"Investigation completed in {result.elapsed_seconds:.1f} seconds", style="bold green"
        )
        width = shutil.get_terminal_size((160, 40)).columns
        if width < 100:
            self.console.print(
                "Compact layout active; use 150–180 columns for screenshot output.",
                style="dim yellow",
            )
        self.console.print(
            "HolmesGPT Investigation Console • Custom Presentation Layer", style="dim cyan"
        )
