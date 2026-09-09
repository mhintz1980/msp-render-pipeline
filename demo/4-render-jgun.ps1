#Requires -Version 5.1
<#
    OPTIONAL - a second product through the identical pipeline.

    jgun-full.glb is a ~250 mm pneumatic torque wrench: a hundred times smaller
    than the RL300 package, a different file format, and 36 untouched CAD
    materials. Nothing in the pipeline was rewritten for it - it is another
    manifest.

    There is no background plate for this tool yet, so this produces the
    transparent master render only. Adding an environment is the same three-line
    edit described in README.md.
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  BONUS  -  JGun torque wrench  -  Product render, no background" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

python -m msp_render_cli run "jobs/jgun_01_no-background.json"
if ($LASTEXITCODE -ne 0) { Write-Host "Render failed." -ForegroundColor Red; exit $LASTEXITCODE }

$beauty = Join-Path $root "output\jgun_01_no-background\beauty.png"
Write-Host ""
Write-Host "Transparent master render:" -ForegroundColor Green
Write-Host "  $beauty"
Write-Host ""
Start-Process $beauty
