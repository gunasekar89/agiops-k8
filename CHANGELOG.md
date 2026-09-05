# Changelog

## 0.2.0

- Add authenticated Alertmanager webhook ingestion and fingerprint deduplication.
- Add deterministic safety policy, complete risk factors, and a hard maximum score of 25.
- Add an explicit `auto_heal=true` alert opt-in requirement.
- Add a single allowlisted remediation for stale, redundant Deployment pods.
- Add immediate preflight revalidation and replacement readiness verification.
- Add observe and automatic modes, bounded request/job limits, and escalation outcomes.
- Add namespace-scoped healer RBAC, Deployment, Service, NetworkPolicy, and Helm options.

## 0.1.0

- Initial HolmesGPT-powered, read-only Kubernetes investigation console.
