"""Command-line entrypoint."""

import argparse
import sys
from typing import Optional

from rich.console import Console

from .analyzer import InvestigationAnalyzer
from .config import Config
from .holmes import HolmesClient, HolmesError
from .kubernetes import KubernetesCollector, KubernetesError
from .ui.dashboard import Dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="holmes-console",
        description="Read-only Kubernetes investigations powered by the real HolmesGPT CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate", help="Investigate an unhealthy workload")
    investigate.add_argument("--namespace", "-n", required=True, help="Kubernetes namespace")
    target = investigate.add_mutually_exclusive_group()
    target.add_argument("--pod", help="Pod name; omit to discover an unhealthy pod")
    target.add_argument("--deployment", help="Deployment whose pod should be investigated")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(highlight=False, soft_wrap=False)
    error_console = Console(stderr=True, highlight=False)
    config = Config.from_env()
    collector = KubernetesCollector(config.kubectl, max_log_chars=config.max_log_chars)
    holmes = HolmesClient(config.holmes, config.timeout_seconds)
    try:
        collector.check_connectivity()
        pod = args.pod
        if args.deployment:
            pod = collector.resolve_deployment_pod(args.namespace, args.deployment)
        elif not pod:
            unhealthy = collector.discover_unhealthy_pods(args.namespace)
            if not unhealthy:
                raise KubernetesError(f"No unhealthy pods found in namespace {args.namespace}")
            pod = unhealthy[0]
            if len(unhealthy) > 1:
                console.print(
                    f"Found {len(unhealthy)} unhealthy pods; investigating {pod}.", style="yellow"
                )
        dashboard = Dashboard(console)
        dashboard.show_context(pod, args.namespace)
        analyzer = InvestigationAnalyzer(collector, holmes)
        result = analyzer.investigate(args.namespace, pod, dashboard.step_succeeded)
        dashboard.render(result)
        return 0
    except (KubernetesError, HolmesError) as exc:
        error_console.print(f"Error: {exc}", style="bold red")
        return 2
    except KeyboardInterrupt:
        error_console.print("Investigation cancelled.", style="yellow")
        return 130


if __name__ == "__main__":
    sys.exit(main())
