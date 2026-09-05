from rich.panel import Panel

from ..models import HolmesAnalysis


def summary_panel(analysis: HolmesAnalysis) -> Panel:
    value = analysis.summary if analysis.structured else "See AI investigation output above."
    return Panel(value, border_style="green", padding=(1, 2))
