# Aegis Holmes — Kubernetes Investigation Console

Aegis Holmes is a production-oriented, read-only terminal console for real Kubernetes incident investigation. **HolmesGPT performs the AI investigation. This repository provides Kubernetes evidence collection, deterministic validation, secret redaction, orchestration, and a custom terminal presentation layer.** The dashboard is not an official HolmesGPT native UI.

The application calls the supported `holmes ask "..."` CLI as an external process. It does not use private HolmesGPT Python internals and never fabricates unavailable evidence or analysis.

## Architecture

```text
User → holmes-console
         ├─ kubectl collector (metadata, state, logs, events, ownership)
         ├─ HolmesGPT (`holmes ask`) performs the real investigation
         ├─ deterministic evidence validator
         ├─ redaction engine
         └─ fixed Rich terminal dashboard
```

All Kubernetes operations are read-only. The console uses `get`, `describe`, and `logs`; it never creates, patches, deletes, or execs into workload resources.

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

The collector never reads Kubernetes `Secret` resources. A defense-in-depth redaction engine strips likely passwords, tokens, API keys, authorization headers, certificates, and private keys before Holmes/process errors or collected data reach the dashboard. Avoid enabling shell tracing when provider credentials are present.

## Container image

The image installs this console, `kubectl`, and the published HolmesGPT CLI package:

```bash
docker build -t holmes-console .
docker run --rm -it \
  -e OPENAI_API_KEY \
  -v "$HOME/.kube:/home/console/.kube:ro" \
  holmes-console investigate --namespace holmes-demo
```

For production, pin the base image and `HOLMES_VERSION` build argument according to your dependency policy. The current default is documented in the Dockerfile.

## In-cluster operation

The `deploy/` manifests contain a ServiceAccount, least-privilege read-only ClusterRole and binding, and a one-shot Job. They do not grant `cluster-admin` and deliberately omit access to Secrets. Review and adapt them before use:

```bash
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/serviceaccount.yaml
kubectl apply -f deploy/rbac.yaml
# Create holmes-provider-credentials securely using your platform process.
kubectl apply -f deploy/job.yaml
kubectl logs -n holmes-system job/holmes-console
```

The in-cluster process and HolmesGPT both authenticate to Kubernetes through the mounted ServiceAccount token, matching HolmesGPT's [documented Kubernetes authentication model](https://holmesgpt.dev/latest/data-sources/builtin-toolsets/kubernetes/). A basic Helm chart is available under `deploy/helm/`.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make check
holmes-console --help
```

Tests cover parsing, malformed HolmesGPT output, redaction, Kubernetes extraction, evidence validation, missing dependencies, connectivity and not-found errors, and narrow/wide rendering. Live cluster and genuine HolmesGPT tests are integration checks and run only where those external systems and credentials exist.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `HOLMES_CONSOLE_KUBECTL` | `kubectl` | kubectl executable path |
| `HOLMES_CONSOLE_HOLMES` | `holmes` | HolmesGPT executable path |
| `HOLMES_CONSOLE_TIMEOUT` | `300` | HolmesGPT timeout in seconds |
| `HOLMES_CONSOLE_MAX_LOG_CHARS` | `24000` | Maximum collected log characters |

## License

Apache License 2.0. See `LICENSE`.
