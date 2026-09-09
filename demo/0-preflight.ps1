#Requires -Version 5.1
<#
    Run this BEFORE the demo (and again five minutes before you present).

    It validates every manifest, confirms that Blender, the CAD file and both
    background plates are where the manifests say they are, and runs the test
    suite. It renders nothing, so it takes a couple of seconds.
#>

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  MSP RENDER PIPELINE  -  PRE-FLIGHT" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan

$failed = 0

Write-Host ""
Write-Host "--- Test suite ---" -ForegroundColor Cyan
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { $failed++ }

foreach ($job in @("rl300_01_no-background",
                   "rl300_02_studio-dark",
                   "rl300_03_excavation-pit")) {
    Write-Host ""
    Write-Host "--- $job ---" -ForegroundColor Cyan
    python -m msp_render_cli validate "jobs/$job.json"
    if ($LASTEXITCODE -ne 0) { $failed++ }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "=======================================================================" -ForegroundColor Green
    Write-Host "  ALL CHECKS PASSED - you are clear to run the demo." -ForegroundColor Green
    Write-Host "=======================================================================" -ForegroundColor Green
} else {
    Write-Host "=======================================================================" -ForegroundColor Red
    Write-Host "  $failed CHECK(S) FAILED - fix before presenting." -ForegroundColor Red
    Write-Host "=======================================================================" -ForegroundColor Red
    exit 1
}
