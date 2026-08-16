<#
.SYNOPSIS
Preserves and resets the .adsPcells cache in one ADS workspace.

.DESCRIPTION
ADS must be completely closed before this script is run. The script validates
the workspace, asks for confirmation, and renames .adsPcells to a timestamped
backup. It does not delete the cache.

.EXAMPLE
./Reset-AdsPcellsCache.ps1 -WorkspacePath "C:\work\example_wrk"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkspacePath
)

$ErrorActionPreference = "Stop"

$resolvedWorkspace = (Resolve-Path -LiteralPath $WorkspacePath).Path
$workspaceMarker = Join-Path $resolvedWorkspace "de_sim.cfg"

if (-not (Test-Path -LiteralPath $workspaceMarker -PathType Leaf)) {
    throw "Refusing to continue: de_sim.cfg was not found in '$resolvedWorkspace'."
}

$cachePath = Join-Path $resolvedWorkspace ".adsPcells"
if (-not (Test-Path -LiteralPath $cachePath -PathType Container)) {
    Write-Host "No .adsPcells directory exists in '$resolvedWorkspace'. Nothing changed."
    exit 0
}

Write-Host "ADS must be completely closed for workspace:"
Write-Host "  $resolvedWorkspace"
$confirmation = Read-Host "Type CLOSED to confirm that ADS is not running"
if ($confirmation -cne "CLOSED") {
    Write-Host "Cancelled. Nothing changed."
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = "$cachePath.stale-$timestamp"
$counter = 1
while (Test-Path -LiteralPath $backupPath) {
    $backupPath = "$cachePath.stale-$timestamp-$counter"
    $counter += 1
}

Move-Item -LiteralPath $cachePath -Destination $backupPath
Write-Host "Cache preserved as:"
Write-Host "  $backupPath"
Write-Host "For a standalone VS Code run, leave ADS closed and pass --workspace."
Write-Host "For value-only changes, run de_generated_scripts/refresh_rfpro_view.py normally."
Write-Host "For renamed/added/removed/type-changed parameters, use --rebuild-schema."
Write-Host "Open ADS only after the standalone refresh or rebuild completes."
