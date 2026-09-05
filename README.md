# Aegis Holmes — Kubernetes Investigation Console

*Agentic Generative Intelligence for Runtime*

Aegis Holmes is a production-oriented Kubernetes investigation and guarded alert-healing service. **HolmesGPT performs the AI investigation. This repository provides Kubernetes evidence collection, deterministic validation, risk scoring, policy-controlled remediation, recovery verification, secret redaction, orchestration, and a custom terminal presentation layer.** The dashboard is not an official HolmesGPT native UI.

The application calls the supported `holmes ask "..."` CLI as an external process. It does not use private HolmesGPT Python internals and never fabricates unavailable evidence or analysis.

## Architecture

```text
User → holmes-console
         ├─ kubectl collector (metadata, state, logs, events, ownership)
         ├─ HolmesGPT (`holmes ask`) performs the real investigation
         ├─ deterministic evidence validator
         ├─ redaction engine
         └─ fixed Rich terminal dashboard

Alertmanager → authenticated alert-healer webhook
                 ├─ the same investigation and validation pipeline
                 ├─ deterministic safety policy and risk score
                 ├─ code-defined remediation allowlist
                 ├─ Kubernetes recovery verification
                 └─ stop and escalate on any unsafe or failed outcome
```

The investigation console is always read-only. Version 2's Alert Healer can receive one narrowly scoped `delete pods` permission in explicitly selected namespaces. It never executes commands proposed by HolmesGPT and never creates, patches, scales, or edits workload resources.

## Prerequisites

- Python 3.9+
- `kubectl`, with a working current context
- HolmesGPT CLI (`holmes`)
- Credentials for a HolmesGPT-supported provider

Install HolmesGPT using its [official CLI installation guide](https://holmesgpt.dev/latest/installation/cli-installation/) or the published `holmesgpt` package. Confirm the exact interface available on the target machine:

```bash
holmes ask --help
```

For example, configure OpenAI without putting credentials in files:

```bash
export OPENAI_API_KEY='...'
```

Other supported providers use their documented environment variables.

## Install from GitHub

```bash
git clone https://github.com/gunasekar89/agiops-k8.git
cd agiops-k8
./install.sh
```

`install.sh` verifies Python, `kubectl`, `holmes`, and Kubernetes connectivity. It installs only the local Python application into `.venv` and links its command into `~/.local/bin`. It does not install cluster resources.

If `~/.local/bin` is not on `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Investigate

Investigate one pod:

```bash
holmes-console investigate --namespace holmes-demo --pod web-app-xxxx
```

Discover unhealthy pods and investigate the first result:

```bash
holmes-console investigate --namespace holmes-demo
```

Investigate a pod owned by a deployment:

```bash
holmes-console investigate --namespace payments --deployment payment-api
```

The alias `aegis-holmes` supports the same arguments. Use a 150–180-column terminal for screenshot-ready output; narrower terminals wrap safely.

## Version 2: guarded Alert Healer

The healer accepts Alertmanager webhook batches and returns `202 Accepted`. Each alert becomes an investigation job, deduplicated using Alertmanager's fingerprint. Query the job endpoint for the diagnosis, evidence validation, complete risk calculation, selected policy action, execution status, and recovery result.

Job state and fingerprint deduplication are process-local and bounded to 1,000 records. Deploy one healer replica, export completed results to your log platform, and expect Alertmanager to retry after a pod restart. Every retry still passes the complete evidence, preflight, and risk policy again.

Start in observe mode, which calculates risk and proposes safe actions without modifying Kubernetes:

```bash
export HOLMES_HEALER_WEBHOOK_TOKEN='use-a-long-random-secret'
alert-healer --host 127.0.0.1 --mode observe --max-risk-score 25
```

Once observe-mode evidence is reviewed, automatic mode requires an explicit operator choice:

```bash
alert-healer --host 0.0.0.0 --mode automatic --max-risk-score 25
```

The safety threshold has a non-overridable maximum of `25`. Raising it above 25 causes startup to fail. Automatic remediation requires all of the following:

- HolmesGPT's diagnostic signal is independently `CONFIRMED` by Kubernetes evidence.
- The evidence contains a stale-runtime signal such as `ContainerStatusUnknown` or `NodeLost`.
- The pod is verified as owned by a Deployment.
- The Deployment has at least two desired replicas and at least one available peer.
- The namespace is neither protected nor production-like.
- The incoming alert explicitly contains `auto_heal="true"`.
- The final deterministic risk score is at or below the configured threshold.
- The selected action is exactly `recycle_pod`; arbitrary LLM commands are never accepted.

CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending/scheduling failures, connectivity failures, unknown owners, StatefulSets, single replicas, and production namespaces remain diagnosis-and-escalation cases. Restarting these automatically can hide or amplify the underlying problem.

Webhook request example:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/alerts \
  -H "Authorization: Bearer $HOLMES_HEALER_WEBHOOK_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "commonLabels": {"namespace": "staging"},
    "alerts": [{
      "status": "firing",
      "fingerprint": "example-1",
      "labels": {"pod": "web-app-xxxx"}
    }]
  }'
```

Check the returned job ID:

```bash
curl -H "Authorization: Bearer $HOLMES_HEALER_WEBHOOK_TOKEN" \
  http://127.0.0.1:8080/api/v1/investigations/<job-id>
```

If execution or recovery verification fails, the healer stops all further mutation and marks the job `ESCALATED`. Pod recreation is controller-managed and cannot restore the exact deleted pod, so this action uses the architecture's “rollback **or escalate**” path.

## Safe demo incidents

```bash
kubectl apply -f demo/crashloop.yaml
kubectl get pods -n holmes-demo
holmes-console investigate --namespace holmes-demo
```

Additional deliberately broken workloads are provided in `demo/oomkilled.yaml`, `demo/imagepullbackoff.yaml`, and `demo/pending-pod.yaml`. These are never installed automatically. Remove the demo namespace when finished:

```bash
kubectl delete namespace holmes-demo
```

## Evidence and validation

The independent collector captures pod phase, node, readiness, container states, waiting and termination reasons, restart counts, exit codes, images, owner references, events, current logs, previous logs, and `kubectl describe` output.

The validator looks for known diagnostic signals in HolmesGPT's stated root cause and then checks those signals against collected Kubernetes evidence. It reports:

- `CONFIRMED`: every recognized claim has independent supporting evidence.
- `PARTIAL`: only some recognized claims are independently supported.
- `UNVERIFIED`: no recognized claim is supported, or no deterministic claim could be extracted.

This validator is intentionally conservative. It is not a second LLM and does not certify general correctness.

## Secret safety

The collector never reads Kubernetes `Secret` resources. A defense-in-depth redaction engine strips likely passwords, tokens, API keys, authorization headers, certificates, and private keys before Holmes/process errors or collected data reach the dashboard or webhook result. Webhook endpoints require a constant-time-compared Bearer token, request bodies are limited to 1 MiB, and access logging is disabled. Avoid enabling shell tracing when credentials are present.

## Container image

The image installs this console, `kubectl`, and the published HolmesGPT CLI package:

```bash
docker build -t holmes-console .
docker run --rm -it \
  -e OPENAI_API_KEY \
  -v "$HOME/.kube:/home/console/.kube:ro" \
  holmes-console investigate --namespace holmes-demo
```

Run the webhook service from the same image by overriding its entrypoint:

```bash
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY \
  -e HOLMES_HEALER_WEBHOOK_TOKEN \
  --entrypoint alert-healer \
  holmes-console --host 0.0.0.0 --mode observe
```

For production, pin the base image and `HOLMES_VERSION` build argument according to your dependency policy. The current default is documented in the Dockerfile.

## In-cluster operation

The `deploy/` manifests contain a ServiceAccount, least-privilege read-only ClusterRole and binding, a one-shot investigation Job, and an optional healer Deployment. They do not grant `cluster-admin` and deliberately omit access to Secrets. The healer write Role is namespace-scoped and permits only `delete` on pods. Review and adapt all namespaces before use:

```bash
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/serviceaccount.yaml
kubectl apply -f deploy/rbac.yaml
# Create holmes-provider-credentials securely using your platform process.
kubectl apply -f deploy/job.yaml
kubectl logs -n holmes-system job/holmes-console
```

The supplied Alert Healer manifest starts in `observe` mode. Add the write Role and switch to `automatic` only after reviewing observed decisions:

```bash
kubectl apply -f deploy/healer-rbac.yaml
kubectl apply -f deploy/healer-deployment.yaml
kubectl apply -f deploy/networkpolicy.yaml
kubectl get pods -n holmes-system
```

`deploy/alertmanager-receiver.example.yaml` shows the receiver and an `auto_heal="true"` routing matcher. Store both `OPENAI_API_KEY` and `WEBHOOK_TOKEN` in `holmes-provider-credentials` through your platform's secret-management process; do not commit their values.

The in-cluster process and HolmesGPT both authenticate to Kubernetes through the mounted ServiceAccount token, matching HolmesGPT's [documented Kubernetes authentication model](https://holmesgpt.dev/latest/data-sources/builtin-toolsets/kubernetes/). A basic Helm chart is available under `deploy/helm/`.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make check
holmes-console --help
```

Tests cover parsing, malformed HolmesGPT output, redaction, Kubernetes extraction, evidence validation, risk-policy boundaries, the hard safety cap, command allowlisting, Alertmanager parsing and deduplication, webhook authentication, missing dependencies, connectivity and not-found errors, and narrow/wide rendering. Live cluster and genuine HolmesGPT tests are integration checks and run only where those external systems and credentials exist.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `HOLMES_CONSOLE_KUBECTL` | `kubectl` | kubectl executable path |
| `HOLMES_CONSOLE_HOLMES` | `holmes` | HolmesGPT executable path |
| `HOLMES_CONSOLE_TIMEOUT` | `300` | HolmesGPT timeout in seconds |
| `HOLMES_CONSOLE_MAX_LOG_CHARS` | `24000` | Maximum collected log characters |
| `HOLMES_HEALER_WEBHOOK_TOKEN` | required | Bearer token protecting healer HTTP endpoints |

## License

Apache License 2.0. See `LICENSE`.
