# Scene preparation — T01/T02

This implements the `scene-prep` module in the approved StudioMark plan
(Second Brain vault: `04-Projects/StudioMark-Pipeline/planning/2026-09-10/plan.md`;
the plan is not committed to this repository).
The operator supplies one curated `.blend`. The preparer must reject missing or unsupported
dependencies, write a typed audit report, preserve the original bytes, and hash the saved
prepared file. `prepared` means local packing succeeded; it does **not** mean G0 isolation,
image parity, visual acceptance, or cloud readiness passed.

## Policy

- Pin Blender **5.1.1**, build **b70da489d7f4**. Start with factory settings and autoexec
  disabled; open with `use_scripts=False`. A different runtime fails explicitly.
- Support local scene data, ordinary single-file still images, generated images stored by
  Blender, and built-in/packable fonts. Force image decoding before packing.
- Reject linked libraries (even packed), movie/sequence/tiled images, external media,
  volume/cache/particle/simulation data, text/scripts, drivers, scripted shaders, geometry
  nodes, and compositor file outputs. Do not silently remove them or substitute content.
  Unknown external paths also block preparation. This is a deliberately narrow allowlist,
  not a general Blender dependency packer or an untrusted-file sandbox.
- Audit all datablocks, including unused ones, without pruning geometry/materials.
- Record and clear **only `LibraryWeakReference.filepath` metadata** on appended local IDs
  in the prepared copy. These paths let Blender reuse previously appended IDs; they are
  not linked-library inputs. RL300 has seven such mesh references to its former export
  file. Keep the original path and ID name in the local audit. Never classify arbitrary
  paths as harmless merely because their string matches a weak reference.
- Re-enumerate external paths after metadata cleanup and packing. In the pinned runtime,
  `bpy.utils.blend_paths(packed=False)` excludes packed data; older API documentation
  describes different semantics. Real packed/missing-source fixtures enforce this.
- Write only to a new evidence directory. Existing directories fail to prevent stale
  successful reports from being reused. Check source identity again before returning success.
- Reports and Blender logs contain local paths. Keep them local; a later cloud adapter
  must sanitize its own records. Never infer image fidelity from a matching file hash.

Blender's [packed-data manual](https://docs.blender.org/manual/en/5.0/files/blend/packed_data.html)
documents packing limits. The installed runtime and integration fixtures are authoritative
for this pinned implementation's API behavior.

## Commands

From `C:/Projects/msp-render-pipeline-scene-prep` in PowerShell:

```powershell
python -m venv --system-site-packages .venv
./.venv/Scripts/python.exe -m pip install -r requirements-test.txt
# NumPy and Pillow are the existing renderer test prerequisites.
$env:MSP_BLENDER_BIN = 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/prepare_scene.py `
  --source cad/RL300-SAFE-photoreal.blend `
  --output-dir output/verification/rl300-prepared-v1/accepted-preparation `
  --blender-bin $env:MSP_BLENDER_BIN
```

The script uses only Python/Blender standard libraries. [jsonschema 4.26.0](https://pypi.org/project/jsonschema/4.26.0/)
is a test-only addition; the tests validate each report against `prepared_scene.schema.json`.
Exit 0 means locally prepared; exit 1 means a typed blocked report; exit 2 means invalid CLI
arguments or an existing output directory. Missing Blender is a test error, never a skip.

Outputs: `prepared.blend` on success, `preparation-report.json`, and local `blender.log`.
All are under ignored `output/`. A report with status `blocked` authorizes no downstream work,
even if a process failure left an incomplete file in its evidence directory.

## Verification and remaining gates

Real Blender fixtures cover missing, corrupt, packed, generated and sequenced image inputs,
disabled embedded scripts, linked versus appended data, source identity, saved hashes,
unavailable runtime, and refusal to reuse evidence. The existing renderer/compositor suite
must remain green. Fixture construction and reports are temporary; do not replace demo images.

T03 must reopen the payload in Linux with source directories inaccessible, capture evaluated
structure, render the fixed reference and negative controls, freeze measured tolerances, and
obtain Mark's reference acceptance. No visual or cloud acceptance is implied by this document.

**T03 is complete as of 2026-09-13.** All five clauses are satisfied by the v12
evidence; Mark accepted the studio-dark v12 reference for source `115fd725…`. See
[the acceptance record](rl300-parity.md#2026-09-13--v12-owner-acceptance-and-t03-complete).
T04 inherits that reference and must compare against it by **pixel digest**, not
file hash.
