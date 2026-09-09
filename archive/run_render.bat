@echo off
echo =======================================================================
echo   MSP Serverless CAD Render Pipeline - Myers-Seth Pumps
echo =======================================================================
echo.
echo Launching Modal serverless render on NVIDIA L4 cloud GPU...
echo Target: RL300-SAFE-render_ready.blend
echo.
uv run --python 3.13 -m modal run render_worker.py --manifest examples/rl300_blend_render_ready.json
echo.
echo =======================================================================
echo Render complete! Passes saved to: .\output\rl300_render_ready\
echo =======================================================================
pause
