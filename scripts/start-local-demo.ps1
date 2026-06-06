param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$RunSmoke
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$BundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

function Test-Url {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Resolve-Node {
  if (Test-Path -LiteralPath $BundledNode) {
    return $BundledNode
  }

  $nodeCommand = Get-Command node -ErrorAction SilentlyContinue

  if ($nodeCommand) {
    return $nodeCommand.Source
  }

  throw "Node.js was not found. Install Node.js, or run inside the Codex bundled runtime."
}

function Start-Backend {
  $healthUrl = "http://127.0.0.1:$($BackendPort)/api/health"

  if (Test-Url $healthUrl) {
    Write-Host "Backend already running: $healthUrl"
    return
  }

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue

  if (-not $pythonCommand) {
    throw "Python was not found. Install Python and backend/requirements.txt first."
  }

  $previousFrontendPort = $env:FRONTEND_PORT
  $env:FRONTEND_PORT = "$FrontendPort"
  try {
    Start-Process `
      -FilePath $pythonCommand.Source `
      -ArgumentList "main.py", "-p", "$BackendPort", "--frontend-port", "$FrontendPort" `
      -WorkingDirectory $BackendDir `
      -WindowStyle Hidden
  } finally {
    $env:FRONTEND_PORT = $previousFrontendPort
  }

  Write-Host "Starting backend: $healthUrl"
}

function Start-Frontend {
  $frontendUrl = "http://127.0.0.1:$($FrontendPort)"

  if (Test-Url $frontendUrl) {
    Write-Host "Frontend already running: $frontendUrl"
    return
  }

  $node = Resolve-Node
  $viteBin = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"

  if (-not (Test-Path -LiteralPath $viteBin)) {
    throw "Frontend dependencies were not found. Run npm install under frontend/ first."
  }

  $previousApiBaseUrl = $env:VITE_API_BASE_URL
  $env:VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort"
  try {
    Start-Process `
      -FilePath $node `
      -ArgumentList $viteBin, "--host", "127.0.0.1", "--port", "$FrontendPort" `
      -WorkingDirectory $FrontendDir `
      -WindowStyle Hidden
  } finally {
    $env:VITE_API_BASE_URL = $previousApiBaseUrl
  }

  Write-Host "Starting frontend: $frontendUrl"
}

Start-Backend
Start-Frontend

Write-Host ""
Write-Host "Demo URLs:"
Write-Host "  Frontend: http://127.0.0.1:$($FrontendPort)"
Write-Host "  Backend health: http://127.0.0.1:$($BackendPort)/api/health"
Write-Host "  Stop demo: .\scripts\stop-local-demo.ps1"
Write-Host ""
Write-Host "Example input:"
Write-Host "  docs/examples/rain-letter-novel.txt"
Write-Host ""
Write-Host "Suggested demo flow:"
Write-Host "  1. Open the frontend page."
Write-Host "  2. Click Import File and select docs/examples/rain-letter-novel.txt."
Write-Host "  3. Click Generate YAML."
Write-Host "  4. Click Validate YAML and confirm the structure is valid."
Write-Host "  5. Click Copy YAML or Download YAML."

if ($RunSmoke) {
  $node = Resolve-Node
  Write-Host ""
  Write-Host "Running demo smoke test..."
  & $node (Join-Path $RepoRoot "scripts\e2e-smoke.mjs")
}
