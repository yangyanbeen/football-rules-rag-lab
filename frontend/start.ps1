[CmdletBinding()]
param([switch]$InstallDependencies, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $ProjectRoot 'scripts/run_baseline_check.ps1') -InstallDependencies:$InstallDependencies -CheckOnly:$CheckOnly
