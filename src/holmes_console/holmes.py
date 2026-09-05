"""Stable external-process adapter for the supported HolmesGPT CLI."""

import re
import shutil
import subprocess

from .models import NOT_AVAILABLE, HolmesAnalysis
from .redaction import RedactionEngine


class HolmesError(RuntimeError):
    pass


class HolmesClient:
    def __init__(self, executable: str = "holmes", timeout: int = 300) -> None:
        self.executable = executable
        self.timeout = timeout
        self.redactor = RedactionEngine()

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def ask(self, pod: str, namespace: str, deployment: str = "") -> HolmesAnalysis:
        target = f"pod {pod}" if pod else f"deployment {deployment}"
        prompt = (
            f"Investigate why {target} in namespace {namespace} is unhealthy.\n\n"
            "Perform a Kubernetes root-cause investigation. Validate your conclusion using "
            "Kubernetes resources, events, status, configuration and logs available to you.\n\n"
            "Return these exact sections without inventing unavailable information:\n\n"
            "ROOT_CAUSE:\n\nEVIDENCE:\n\nRECOMMENDED_ACTIONS:\n\nSUMMARY:"
        )
        if not self.available():
            raise HolmesError(
                f"HolmesGPT CLI '{self.executable}' was not found. Install HolmesGPT and ensure "
                "the 'holmes' executable is on PATH."
            )
        try:
            completed = subprocess.run(
                [self.executable, "ask", prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HolmesError(f"HolmesGPT timed out after {self.timeout} seconds") from exc
        safe_stdout = self.redactor.redact(completed.stdout)
        safe_stderr = self.redactor.redact(completed.stderr)
        if completed.returncode:
            detail = safe_stderr.strip() or safe_stdout.strip() or "No diagnostic output"
            raise HolmesError(f"HolmesGPT exited with code {completed.returncode}: {detail}")
        return parse_holmes_output(safe_stdout)


_SECTION = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?"
    r"(ROOT[ _-]?CAUSE|EVIDENCE|RECOMMENDED[ _-]?ACTIONS|SUMMARY)\s*:?[ \t]*$"
)
_NAMES: dict[str, str] = {
    "ROOTCAUSE": "root_cause",
    "EVIDENCE": "evidence",
    "RECOMMENDEDACTIONS": "recommended_actions",
    "SUMMARY": "summary",
}


def parse_holmes_output(output: str) -> HolmesAnalysis:
    raw = output.strip()
    matches = list(_SECTION.finditer(raw))
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        normalized = re.sub(r"[ _-]", "", match.group(1)).upper()
        key = _NAMES[normalized]
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        values[key] = raw[match.end() : end].strip() or NOT_AVAILABLE
    structured = "root_cause" in values and len(values) >= 2
    return HolmesAnalysis(
        root_cause=values.get("root_cause", NOT_AVAILABLE),
        evidence=values.get("evidence", NOT_AVAILABLE),
        recommended_actions=values.get("recommended_actions", NOT_AVAILABLE),
        summary=values.get("summary", NOT_AVAILABLE),
        raw_output=raw,
        structured=structured,
    )
