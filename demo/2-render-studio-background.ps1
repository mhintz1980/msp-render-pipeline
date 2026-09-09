#Requires -Version 5.1
<#
    DEMO STEP 2 of 3 - Same machine, lit by a background photograph.

    env_studio-dark.png is loaded twice: once as the world environment texture,
    so every reflection and every bounce of light on the machine comes from the
    photograph itself (image-based / HDRI lighting), and once as the background
    plate the finished render is seated on.

    That is what makes it look real. In step 1 the machine was lit by synthetic
    softboxes that knew nothing about where it would end up. Here the lighting
    and the environment are the same image, so the highlights land where the
    lights in the photo actually are.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 2/3  -  RL300-SAFE  -  Dark studio plate + HDRI lighting" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

python -m msp_render_cli run "jobs/rl300_02_studio-dark.json"
if ($LASTEXITCODE -ne 0) { Write-Host "Render failed." -ForegroundColor Red; exit $LASTEXITCODE }

$final = Join-Path $root "output\rl300_02_studio-dark\final_rl300_02_studio-dark.png"
Write-Host ""
Write-Host "Finished marketing image:" -ForegroundColor Green
Write-Host "  $final"
Write-Host ""
Start-Process $final
