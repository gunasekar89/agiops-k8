"""Runtime configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kubectl: str = "kubectl"
    holmes: str = "holmes"
    timeout_seconds: int = 300
    max_log_chars: int = 24_000

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            kubectl=os.getenv("HOLMES_CONSOLE_KUBECTL", "kubectl"),
            holmes=os.getenv("HOLMES_CONSOLE_HOLMES", "holmes"),
            timeout_seconds=int(os.getenv("HOLMES_CONSOLE_TIMEOUT", "300")),
            max_log_chars=int(os.getenv("HOLMES_CONSOLE_MAX_LOG_CHARS", "24000")),
        )
