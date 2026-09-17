# VPS Sync Mirror (Hermes)

A Hermes agent VPS mirrors this repo automatically since 2026-09-17:

- Pull every 5 min, fast-forward only (never merges). Divergence pages the human; it never auto-resolves.
- All renders on the VPS go through a gated runner that syncs first and REFUSES to run if behind origin/main.
- Zip snapshot `msp_render_pipeline_verified.zip` from Google Drive (Sep 7) was imported on branch
  `archive/drive-zip-sep7` for provenance; main here supersedes it.

Laptop push -> VPS picks it up within ~5 minutes. Nothing else needed.
