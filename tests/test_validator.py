from holmes_console.models import HolmesAnalysis, KubernetesEvidence, ValidationStatus
from holmes_console.validator import EvidenceValidator


def test_confirms_matching_cluster_evidence():
    evidence = KubernetesEvidence(
        pod="web",
        namespace="demo",
        describe="State: CrashLoopBackOff",
        previous_logs="ERROR: connection refused at db:5432",
    )
    analysis = HolmesAnalysis(
        root_cause="CrashLoopBackOff caused by database connection refused",
        evidence="db unavailable",
    )
    result = EvidenceValidator().validate(analysis, evidence)
    assert result.status is ValidationStatus.CONFIRMED


def test_unverified_when_claim_is_not_in_cluster_evidence():
    evidence = KubernetesEvidence(pod="web", namespace="demo", logs="healthy startup")
    analysis = HolmesAnalysis(root_cause="OOMKilled")
    result = EvidenceValidator().validate(analysis, evidence)
    assert result.status is ValidationStatus.UNVERIFIED


def test_unverified_for_unrecognized_claim():
    evidence = KubernetesEvidence(pod="web", namespace="demo")
    analysis = HolmesAnalysis(root_cause="A novel failure mode")
    assert EvidenceValidator().validate(analysis, evidence).status is ValidationStatus.UNVERIFIED
