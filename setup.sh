#!/usr/bin/env bash
set -euo pipefail

# ---- Config (you can change these) ----
KERNEL_NAME_DEFAULT="MajorityColoring"
# --------------------------------------

# project root = directory where this script lives
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KERNEL_NAME="${1:-$KERNEL_NAME_DEFAULT}"

echo "==> Project root: $PROJECT_ROOT"
echo "==> Kernel name:  $KERNEL_NAME"

# Check Julia
if ! command -v julia >/dev/null 2>&1; then
  echo "ERROR: julia not found in PATH. Install Julia (e.g., via juliaup) and try again."
  exit 1
fi

# Check Jupyter (optional but recommended)
if ! command -v jupyter >/dev/null 2>&1; then
  echo "WARNING: jupyter not found in PATH."
  echo "Install it with: pip install notebook  (or pip install jupyterlab)"
  echo "Continuing anyway (kernel can still be installed)."
fi

echo "==> Instantiating & precompiling Julia project (safe to re-run)..."
julia --project="$PROJECT_ROOT" -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'

echo "==> Installing IJulia (in your project env) and registering kernel..."
julia --project="$PROJECT_ROOT" -e "
  using Pkg
  Pkg.add(\"IJulia\")
  using IJulia

  # Make kernel spec name stable/valid
  kernel = \"$KERNEL_NAME\"
  spec   = lowercase(replace(kernel, r\"[^a-zA-Z0-9_-]\" => \"-\"))

  # This makes Jupyter launch Julia with your repo environment
  env = Dict(\"JULIA_PROJECT\" => \"$PROJECT_ROOT\")

  IJulia.installkernel(kernel; specname=spec, displayname=kernel, env=env)

  println(\"Kernel installed:\")
  println(\"  displayname = \", kernel)
  println(\"  specname    = \", spec)
  println(\"  JULIA_PROJECT= \", \"$PROJECT_ROOT\")
"

echo "==> Done."
echo ""
echo "Next:"
echo "  1) Start Jupyter:   jupyter notebook   (or jupyter lab)"
echo "  2) Choose kernel:   $KERNEL_NAME"
echo ""
echo "Tip: You can rename kernel by running:"
echo "  ./setup.sh \"AnotherName\""
