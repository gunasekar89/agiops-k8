#!/usr/bin/env sh
set -eu

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }

command -v python3 >/dev/null 2>&1 || fail "python3 is required (3.9 or newer)."
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' || fail "Python 3.9 or newer is required."
command -v kubectl >/dev/null 2>&1 || fail "kubectl is required and was not found on PATH."
command -v holmes >/dev/null 2>&1 || fail "HolmesGPT CLI is required; install it so 'holmes' is on PATH."

info "Checking Kubernetes connectivity (read-only)..."
kubectl cluster-info --request-timeout=10s >/dev/null 2>&1 || fail "kubectl cannot connect to the current Kubernetes cluster."

info "Creating isolated Python environment in .venv..."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .

mkdir -p "$HOME/.local/bin"
ln -sf "$(pwd)/.venv/bin/holmes-console" "$HOME/.local/bin/holmes-console"

info "Installed holmes-console. Ensure $HOME/.local/bin is on PATH."
info "Try: holmes-console investigate --namespace <namespace> --pod <pod>"

