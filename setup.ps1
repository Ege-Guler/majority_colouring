$KernelNameDefault = "MajorityColoring"

# Project root = directory where this script lives
$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = Get-Location }

# Use argument if provided, otherwise use default
$KernelName = if ($args[0]) { $args[0] } else { $KernelNameDefault }

Write-Host "==> Project root: $ProjectRoot"
Write-Host "==> Kernel name:  $KernelName"

# Check Julia
if (-not (Get-Command julia -ErrorAction SilentlyContinue)) {
    Write-Error "julia not found in PATH. Install Julia (e.g., via juliaup) and try again."
    exit 1
}

# Check Jupyter (optional)
if (-not (Get-Command jupyter -ErrorAction SilentlyContinue)) {
    Write-Warning "jupyter not found in PATH."
    Write-Host "Install it with: pip install notebook (or jupyterlab)"
}

Write-Host "==> Instantiating & precompiling Julia project..." -ForegroundColor Yellow
julia --project="$ProjectRoot" -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'

Write-Host "==> Installing IJulia and registering kernel..." -ForegroundColor Yellow

$JuliaCommand = @"
using Pkg
Pkg.add(""IJulia"")
using IJulia

kernel = raw""$KernelName""
spec = lowercase(replace(kernel, r""[^a-zA-Z0-9_-]"" => ""-""))

# Make sure Jupyter uses this project
env = Dict(""JULIA_PROJECT"" => raw""$ProjectRoot"")

IJulia.installkernel(kernel; specname=spec, displayname=kernel, env=env)

println(""Kernel installed:"")
println(""  displayname = "", kernel)
println(""  specname    = "", spec)
println(""  JULIA_PROJECT= "", raw""$ProjectRoot"")
"@

julia --project="$ProjectRoot" -e $JuliaCommand

Write-Host "`n==> Done."
Write-Host "Next:"
Write-Host "  1) Start Jupyter:   jupyter notebook"
Write-Host "  2) Choose kernel:   $KernelName"
Write-Host "`nTip: You can rename the kernel by running:"
Write-Host "  .\setup.ps1 `"AnotherName`""