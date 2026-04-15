param(
    [switch]$IncludeDatabases,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Test-InRepo([string]$PathToCheck) {
    if (-not (Test-Path -LiteralPath $PathToCheck)) {
        return $false
    }
    $resolved = (Resolve-Path -LiteralPath $PathToCheck).Path
    return $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)
}

function Remove-SafePath([string]$TargetPath) {
    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return $false
    }

    if (-not (Test-InRepo -PathToCheck $TargetPath)) {
        throw "Refusing to remove path outside repository: $TargetPath"
    }

    if ($WhatIf) {
        Write-Host "[whatif] remove: $TargetPath"
        return $true
    }

    Remove-Item -LiteralPath $TargetPath -Recurse -Force
    Write-Host "[removed] $TargetPath"
    return $true
}

$targets = New-Object System.Collections.Generic.List[string]

# Standard cache directories
$targets.Add((Join-Path $repoRoot ".pytest_cache")) | Out-Null
$targets.Add((Join-Path $repoRoot "__pycache__")) | Out-Null
$targets.Add((Join-Path $repoRoot "app\__pycache__")) | Out-Null
$targets.Add((Join-Path $repoRoot "tests\__pycache__")) | Out-Null
$targets.Add((Join-Path $repoRoot "scripts\__pycache__")) | Out-Null
$targets.Add((Join-Path $repoRoot "agent_eval\__pycache__")) | Out-Null
$targets.Add((Join-Path $repoRoot "scripts\finals\__pycache__")) | Out-Null

# Any nested __pycache__ directories
$nestedPyCache = Get-ChildItem -Path $repoRoot -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
foreach ($path in $nestedPyCache) {
    $targets.Add($path) | Out-Null
}

# Runtime temp files
$targets.Add((Join-Path $repoRoot "tmp_debug.db")) | Out-Null
$targets.Add((Join-Path $repoRoot ".coverage")) | Out-Null

$walAndShm = Get-ChildItem -Path $repoRoot -File -Recurse -Include "*.db-wal", "*.db-shm" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
foreach ($path in $walAndShm) {
    $targets.Add($path) | Out-Null
}

if ($IncludeDatabases) {
    $targets.Add((Join-Path $repoRoot "smart_lab.db")) | Out-Null
}

$removed = 0
$uniqueTargets = $targets | Sort-Object -Unique
foreach ($target in $uniqueTargets) {
    if (Remove-SafePath -TargetPath $target) {
        $removed += 1
    }
}

Write-Host ""
Write-Host "Workspace cleanup complete."
Write-Host "Removed targets: $removed"
Write-Host "Repository root: $repoRoot"
Write-Host "IncludeDatabases: $IncludeDatabases"
Write-Host "WhatIf: $WhatIf"
