#Requires -Version 5.1
<#
    DEMO STEP 3 of 3 - Identical command, completely different environment.

    Nothing changed except which manifest is passed in. The excavation-pit
    photograph now drives the world lighting, and a 5400K key sun is aimed to
    match the shadow direction visible in the plate, so the machine picks up
    warm sunlight and soil bounce instead of studio tungsten.

    New environment = new JSON file. No re-modelling, no re-shading, no
    photo shoot.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 3/3  -  RL300-SAFE  -  Sunlit excavation pit + HDRI lighting" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

python -m msp_render_cli run "jobs/rl300_03_excavation-pit.json"
if ($LASTEXITCODE -ne 0) { Write-Host "Render failed." -ForegroundColor Red; exit $LASTEXITCODE }

$final = Join-Path $root "output\rl300_03_excavation-pit\final_rl300_03_excavation-pit.png"
Write-Host ""
Write-Host "Finished marketing image:" -ForegroundColor Green
Write-Host "  $final"
Write-Host ""
Start-Process $final
