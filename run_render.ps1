Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "  MSP Serverless CAD Render Pipeline - Myers-Seth Pumps" -ForegroundColor Yellow
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Launching Modal serverless render on NVIDIA L4 cloud GPU..." -ForegroundColor Green
Write-Host "Target: RL300-SAFE-render_ready.blend"
Write-Host ""

uv run --python 3.13 -m modal run render_worker.py --manifest examples/rl300_blend_render_ready.json

Write-Host ""
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "Render complete! Passes saved to: .\output\rl300_render_ready\" -ForegroundColor Green
Write-Host "=======================================================================" -ForegroundColor Cyan
