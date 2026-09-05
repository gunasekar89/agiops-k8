import pytest

from holmes_console.models import ValidationResult, ValidationStatus
from holmes_console.redaction import RedactionEngine


@pytest.mark.parametrize(
    "source, secret",
    [
        ("password=hunter2", "hunter2"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret", "eyJhbGciOiJIUzI1NiJ9.secret"),
        ("api_key: sk-test123456", "sk-test123456"),
        ("token=abcdefghijk", "abcdefghijk"),
        ("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", "abc"),
    ],
)
def test_redacts_secrets(source, secret):
    value = RedactionEngine().redact(source)
    assert secret not in value
    assert "[REDACTED]" in value


def test_does_not_redact_normal_diagnostics():
    source = "ERROR connection refused at db:5432"
    assert RedactionEngine().redact(source) == source


def test_preserves_enum_types_in_nested_dataclasses():
    result = ValidationResult(ValidationStatus.CONFIRMED, explanation="token=secret-value")
    RedactionEngine().redact_object(result)
    assert result.status is ValidationStatus.CONFIRMED
    assert "secret-value" not in result.explanation
