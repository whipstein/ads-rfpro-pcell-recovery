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
Write-Host "Restart ADS, keep RFPro closed, and run refresh_rfpro_view.py."
