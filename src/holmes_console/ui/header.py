from rich.align import Align
from rich.panel import Panel
from rich.text import Text


def build_header() -> Panel:
    title = Text()
    title.append("HolmesGPT", style="bold bright_cyan")
    title.append("              AI-Powered Kubernetes Troubleshooting", style="bold white")
    subtitle = Text("Analyze  •  Diagnose  •  Explain  •  Recommend", style="cyan")
    return Panel(
        Align.center(Text.assemble(title, "\n", subtitle)), border_style="cyan", padding=(1, 2)
    )
