"""Defense-in-depth redaction applied before rendering or diagnostic output."""

import re
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


class RedactionEngine:
    REDACTED = "[REDACTED]"
    _patterns = (
        re.compile(r"(?i)(authorization\s*:\s*(?:bearer\s+)?)[^\s,;]+"),
        re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
        re.compile(
            r"(?i)\b(password|passwd|pwd|token|api[_-]?key|client[_-]?secret)"
            r"(\s*[:=]\s*)([^\s,;\]}]+)"
        ),
        re.compile(
            r"(?s)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END "
            r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
        re.compile(r"(?s)-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----"),
        re.compile(r"(?i)(dockerconfigjson\s*[:=]\s*)[^\s,;]+"),
    )

    def redact(self, text: Any) -> str:
        value = str(text) if text is not None else ""
        for index, pattern in enumerate(self._patterns):
            if index in (0, 1, 4, 5):
                value = pattern.sub(
                    lambda m: (m.group(1) if m.lastindex else "") + self.REDACTED, value
                )
            elif index in (2,):
                value = pattern.sub(lambda m: m.group(1) + m.group(2) + self.REDACTED, value)
            else:
                value = pattern.sub(self.REDACTED, value)
        return value

    def redact_object(self, obj: Any) -> Any:
        """Mutate nested dataclass string fields immediately before presentation."""
        if is_dataclass(obj):
            for item in fields(obj):
                value = getattr(obj, item.name)
                if isinstance(value, Enum):
                    continue
                if isinstance(value, str):
                    setattr(obj, item.name, self.redact(value))
                elif is_dataclass(value) or isinstance(value, list):
                    self.redact_object(value)
        elif isinstance(obj, list):
            for value in obj:
                self.redact_object(value)
        return obj
