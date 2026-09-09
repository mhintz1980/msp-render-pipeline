#Requires -Version 5.1
<#
    DEMO STEP 1 of 3 - Render the machine on a transparent background.

    Opens RL300-SAFE-photoreal.blend in headless Blender, applies the studio
    lighting rig and the photoreal shading pass, and renders with Cycles onto a
    transparent film. The result is a clean cut-out: no floor, no backdrop,
    nothing but the machine and its alpha matte.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 1/3  -  RL300-SAFE  -  Product render, no background" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

python -m msp_render_cli run "jobs/rl300_01_no-background.json"
if ($LASTEXITCODE -ne 0) { Write-Host "Render failed." -ForegroundColor Red; exit $LASTEXITCODE }

$beauty = Join-Path $root "output\rl300_01_no-background\beauty.png"
Write-Host ""
Write-Host "Transparent master render:" -ForegroundColor Green
Write-Host "  $beauty"
Write-Host "  (plus mask.png - the alpha matte the compositor uses)"
Write-Host ""
Start-Process $beauty
