from unittest.mock import patch

from holmes_console.cli import main
from holmes_console.holmes import HolmesError
from holmes_console.kubernetes import KubernetesError


def test_connectivity_failure(capsys):
    with patch(
        "holmes_console.cli.KubernetesCollector.check_connectivity",
        side_effect=KubernetesError("unreachable"),
    ):
        assert main(["investigate", "-n", "demo", "--pod", "web"]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_pod_not_found(capsys):
    with (
        patch("holmes_console.cli.KubernetesCollector.check_connectivity"),
        patch(
            "holmes_console.cli.InvestigationAnalyzer.investigate",
            side_effect=KubernetesError("pods web not found"),
        ),
    ):
        assert main(["investigate", "-n", "demo", "--pod", "web"]) == 2
    assert "not found" in capsys.readouterr().err


def test_missing_holmes(capsys):
    with (
        patch("holmes_console.cli.KubernetesCollector.check_connectivity"),
        patch(
            "holmes_console.cli.InvestigationAnalyzer.investigate",
            side_effect=HolmesError("holmes was not found"),
        ),
    ):
        assert main(["investigate", "-n", "demo", "--pod", "web"]) == 2
    assert "holmes was not found" in capsys.readouterr().err
