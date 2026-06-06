param(
  [int[]]$Ports = @(8000, 5173),
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProjectPathPattern = "*$RepoRoot*"
$CommandPatterns = @(
  "main.py",
  "app.main:app",
  "uvicorn",
  "vite.js",
  "e2e-smoke.mjs"
)

function Get-CommandLineProcesses {
  try {
    return @(Get-CimInstance Win32_Process)
  } catch {
    throw "Unable to inspect process command lines. Run PowerShell as a user that can read local process metadata."
  }
}

function Get-ListeningProcessIds {
  $processIds = [System.Collections.Generic.HashSet[int]]::new()

  foreach ($port in $Ports) {
    try {
      $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
    } catch {
      $connections = @()
    }

    foreach ($connection in $connections) {
      if ($connection.OwningProcess -and $connection.OwningProcess -ne $PID) {
        [void]$processIds.Add([int]$connection.OwningProcess)
      }
    }
  }

  return $processIds
}

function Test-DemoCommand {
  param([string]$CommandLine)

  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }

  $hasProjectPath = $CommandLine -like $ProjectPathPattern
  $isBackend = ($CommandLine -like "*main.py*") -or (
    $CommandLine -like "*uvicorn*" -and $CommandLine -like "*app.main:app*"
  )
  $isFrontend = $CommandLine -like "*vite.js*"
  $isSmoke = $CommandLine -like "*e2e-smoke.mjs*"

  return $hasProjectPath -and ($isBackend -or $isFrontend -or $isSmoke)
}

function Test-PortServerCommand {
  param([string]$CommandLine)

  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }

  return ($CommandLine -like "*main.py*") -or
    ($CommandLine -like "*uvicorn*" -and $CommandLine -like "*app.main:app*") -or
    ($CommandLine -like "*vite.js*")
}

function Add-Descendants {
  param(
    [object[]]$AllProcesses,
    [System.Collections.Generic.HashSet[int]]$ProcessIds
  )

  $changed = $true

  while ($changed) {
    $changed = $false

    foreach ($process in $AllProcesses) {
      if (
        $process.ParentProcessId -and
        $ProcessIds.Contains([int]$process.ParentProcessId) -and
        -not $ProcessIds.Contains([int]$process.ProcessId)
      ) {
        [void]$ProcessIds.Add([int]$process.ProcessId)
        $changed = $true
      }
    }
  }
}

$allProcesses = Get-CommandLineProcesses
$listeningProcessIds = Get-ListeningProcessIds
$targetProcessIds = [System.Collections.Generic.HashSet[int]]::new()

foreach ($process in $allProcesses) {
  if ($process.ProcessId -eq $PID) {
    continue
  }

  $commandLine = $process.CommandLine
  $isPortServer = $listeningProcessIds.Contains([int]$process.ProcessId) -and (Test-PortServerCommand $commandLine)

  if ((Test-DemoCommand $commandLine) -or $isPortServer) {
    [void]$targetProcessIds.Add([int]$process.ProcessId)
  }
}

Add-Descendants -AllProcesses $allProcesses -ProcessIds $targetProcessIds

$targets = @(
  $allProcesses |
    Where-Object { $targetProcessIds.Contains([int]$_.ProcessId) } |
    Sort-Object ProcessId |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine
)

if ($targets.Count -eq 0) {
  Write-Host "No local demo processes found for ports: $($Ports -join ', ')."
  exit 0
}

Write-Host "Found $($targets.Count) local demo process(es):"
$targets | Format-Table ProcessId, ParentProcessId, Name, CommandLine -AutoSize

if ($DryRun) {
  Write-Host "Dry run only. Re-run without -DryRun to stop these processes."
  exit 0
}

$stopIds = @($targets | Select-Object -ExpandProperty ProcessId)
Stop-Process -Id $stopIds -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

$remaining = @(
  Get-CommandLineProcesses |
    Where-Object { $targetProcessIds.Contains([int]$_.ProcessId) } |
    Sort-Object ProcessId
)

if ($remaining.Count -gt 0) {
  Write-Warning "Some local demo processes are still running:"
  $remaining | Select-Object ProcessId, ParentProcessId, Name, CommandLine | Format-Table -AutoSize
  exit 1
}

Write-Host "Stopped $($targets.Count) local demo process(es)."
