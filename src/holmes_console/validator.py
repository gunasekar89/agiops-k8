"""Deterministic corroboration of HolmesGPT findings against collected evidence."""

from .models import HolmesAnalysis, KubernetesEvidence, ValidationResult, ValidationStatus

SIGNALS: dict[str, set[str]] = {
    "crashloopbackoff": {"crashloopbackoff", "back-off restarting", "repeatedly terminating"},
    "oomkilled": {"oomkilled", "out of memory", "exit code 137", "exitcode: 137"},
    "imagepull": {"imagepullbackoff", "errimagepull", "failed to pull image"},
    "pending": {
        "pending",
        "failedscheduling",
        "insufficient cpu",
        "insufficient memory",
        "unschedulable",
    },
    "connectivity": {
        "connection refused",
        "could not connect",
        "timeout",
        "timed out",
        "unreachable",
    },
    "dns": {"name or service not known", "no such host", "dns", "nxdomain"},
    "permission": {"forbidden", "permission denied", "unauthorized", "rbac"},
    "stale_runtime": {
        "containerstatusunknown",
        "node lost",
        "nodelost",
        "pod unknown",
    },
}


class EvidenceValidator:
    def validate(self, analysis: HolmesAnalysis, evidence: KubernetesEvidence) -> ValidationResult:
        diagnosis = " ".join((analysis.root_cause, analysis.evidence)).lower()
        corpus = " ".join(
            [
                evidence.phase,
                evidence.describe,
                evidence.logs,
                evidence.previous_logs,
                *[
                    f"{c.state} {c.waiting_reason} {c.termination_reason} {c.exit_code}"
                    for c in evidence.containers
                ],
                *[f"{e.reason} {e.message}" for e in evidence.events],
            ]
        ).lower()
        claimed = {
            category
            for category, terms in SIGNALS.items()
            if any(term in diagnosis for term in terms)
        }
        supported = {
            category for category in claimed if any(term in corpus for term in SIGNALS[category])
        }
        matched_terms = sorted(
            term for category in supported for term in SIGNALS[category] if term in corpus
        )
        if not claimed:
            return ValidationResult(
                ValidationStatus.UNVERIFIED,
                [],
                "No deterministic diagnostic signal could be extracted from the "
                "HolmesGPT conclusion.",
            )
        if supported == claimed:
            status = ValidationStatus.CONFIRMED
            explanation = (
                "All recognized diagnostic signals are independently present in "
                "Kubernetes evidence."
            )
        elif supported:
            status = ValidationStatus.PARTIAL
            explanation = (
                "Some, but not all, recognized diagnostic signals are present in "
                "Kubernetes evidence."
            )
        else:
            status = ValidationStatus.UNVERIFIED
            explanation = (
                "Recognized claims were not independently found in the collected "
                "Kubernetes evidence."
            )
        return ValidationResult(status, matched_terms[:8], explanation)
