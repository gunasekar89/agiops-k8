from unittest.mock import Mock, patch

import pytest

from holmes_console.holmes import HolmesClient, HolmesError


def test_invokes_supported_holmes_ask_interface():
    completed = Mock(
        returncode=0, stdout="ROOT_CAUSE:\nPending\nEVIDENCE:\nFailedScheduling", stderr=""
    )
    client = HolmesClient()
    with (
        patch.object(client, "available", return_value=True),
        patch("subprocess.run", return_value=completed) as run,
    ):
        result = client.ask("web", "demo")
    command = run.call_args.args[0]
    assert command[:2] == ["holmes", "ask"]
    assert "pod web" in command[2]
    assert result.structured


def test_missing_holmes_is_explicit():
    client = HolmesClient("missing-holmes")
    with (
        patch.object(client, "available", return_value=False),
        pytest.raises(HolmesError, match="not found"),
    ):
        client.ask("web", "demo")
