from holmes_console.holmes import parse_holmes_output
from holmes_console.models import NOT_AVAILABLE


def test_parses_expected_sections():
    result = parse_holmes_output(
        "ROOT_CAUSE:\nDatabase unavailable\n\nEVIDENCE:\nConnection refused\n\n"
        "RECOMMENDED_ACTIONS:\n1. Check service\n\nSUMMARY:\nStartup failed"
    )
    assert result.structured
    assert result.root_cause == "Database unavailable"
    assert result.evidence == "Connection refused"
    assert result.summary == "Startup failed"


def test_parses_markdown_headings_and_spaces():
    result = parse_holmes_output("## ROOT CAUSE\nOOMKilled\n## EVIDENCE\nExit code 137")
    assert result.structured
    assert result.root_cause == "OOMKilled"
    assert result.summary == NOT_AVAILABLE


def test_malformed_response_preserves_raw_output():
    raw = "I could not format this, but the pod is pending."
    result = parse_holmes_output(raw)
    assert not result.structured
    assert result.raw_output == raw
    assert result.root_cause == NOT_AVAILABLE
