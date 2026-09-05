"""Investigation orchestration."""

import time
from typing import Callable

from .holmes import HolmesClient
from .kubernetes import KubernetesCollector
from .models import InvestigationResult
from .redaction import RedactionEngine
from .validator import EvidenceValidator


class InvestigationAnalyzer:
    def __init__(self, collector: KubernetesCollector, holmes: HolmesClient):
        self.collector = collector
        self.holmes = holmes
        self.validator = EvidenceValidator()
        self.redactor = RedactionEngine()

    def investigate(
        self, namespace: str, pod: str, progress: Callable[[str], None]
    ) -> InvestigationResult:
        started = time.monotonic()
        progress("Collecting pod details")
        evidence = self.collector.collect(namespace, pod)
        progress("Fetching container logs")
        progress("Checking Kubernetes events")
        progress("Inspecting configuration")
        analysis = self.holmes.ask(pod, namespace)
        progress("Running HolmesGPT investigation")
        validation = self.validator.validate(analysis, evidence)
        result = InvestigationResult(evidence, analysis, validation, time.monotonic() - started)
        return self.redactor.redact_object(result)
