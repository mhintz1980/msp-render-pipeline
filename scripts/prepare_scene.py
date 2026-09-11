"""Prepare a curated still scene with Blender; never overwrite the input or evidence.

Run with normal Python. The internal Blender process audits before packing and
saving a new file. `prepared` is a local packing result, not isolation/visual proof.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

PINNED_VERSION = "5.1.1"
PINNED_BUILD = "b70da489d7f4"


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def new_report(source):
    return {
        "schema_version": 1,
        "status": "blocked",
        "scope": "local_preparation",
        "isolation_verified": False,
        "source": {"path": str(source), "sha256": file_hash(source) if source.is_file() else None},
        "prepared": None,
        "runtime": None,
        "dependencies": [],
        "sanitized_metadata": [],
        "blockers": [],
        "remaining_external_paths": [],
        "scene_summary": None,
        "elapsed_seconds": 0.0,
    }


def block(report, code, resource, detail):
    finding = {"code": code, "resource": resource, "detail": detail}
    if finding not in report["blockers"]:
        report["blockers"].append(finding)


def write_report(output, report):
    temporary = output / "preparation-report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output / "preparation-report.json")


def node_trees(bpy):
    trees = list(bpy.data.node_groups)
    for collection in (bpy.data.materials, bpy.data.worlds, bpy.data.scenes):
        for owner in collection:
            for attr in ("node_tree", "compositing_node_group"):
                tree = getattr(owner, attr, None)
                if tree is not None and tree not in trees:
                    trees.append(tree)
    return trees


def audit(bpy, report):
    """Conservative v1 allowlist: local meshes/materials, still images and fonts."""
    known_paths = set()
    datablocks = [item for prop in bpy.data.bl_rna.properties if prop.type == "COLLECTION"
                  for item in getattr(bpy.data, prop.identifier)]
    for item in datablocks:
        reference = getattr(item, "library_weak_reference", None)
        if reference and reference.filepath and item.library is None:
            report["sanitized_metadata"].append({
                "kind": "library_weak_reference", "datablock": f"{item.bl_rna.identifier}:{item.name}",
                "original_path": reference.filepath, "id_name": reference.id_name,
            })
            reference.filepath = ""

    def dependency(kind, item, builtin=False):
        raw = item.filepath
        packed = getattr(item, "packed_file", None)
        resolved = str(Path(bpy.path.abspath(raw, library=item.library)).resolve()) if raw else None
        if resolved:
            known_paths.add(os.path.normcase(resolved))
        storage = "builtin" if builtin else "packed" if packed else "external"
        digest, size = None, None
        if packed:
            digest, size = hashlib.sha256(packed.data).hexdigest(), packed.size
        elif not builtin:
            if not resolved or not Path(resolved).is_file():
                block(report, "MISSING_DEPENDENCY", f"{kind}:{item.name}", f"Required file is absent: {resolved or raw}")
            else:
                digest, size = file_hash(resolved), Path(resolved).stat().st_size
        report["dependencies"].append({
            "kind": kind, "name": item.name, "original_path": raw,
            "resolved_path": resolved, "storage": storage, "sha256": digest, "size_bytes": size,
        })

    for library in bpy.data.libraries:
        dependency("library", library)
        block(report, "UNSUPPORTED_DEPENDENCY", f"library:{library.name}",
              "Linked libraries require a separate recursive packing/isolation proof; v1 rejects them.")
    for image in bpy.data.images:
        if image.source == "VIEWER":
            continue  # Render Result and Viewer Node are transient output buffers.
        if image.source not in {"FILE", "GENERATED"}:
            block(report, "UNSUPPORTED_DEPENDENCY", f"image:{image.name}", f"Image source {image.source} is not a single still image.")
        if image.source == "GENERATED":
            report["dependencies"].append({
                "kind": "image", "name": image.name, "original_path": image.filepath,
                "resolved_path": None, "storage": "generated", "sha256": None, "size_bytes": None,
            })
        else:
            dependency("image", image)
            if image.is_dirty:
                block(report, "UNSUPPORTED_DEPENDENCY", f"image:{image.name}", "Unsaved image edits require an explicit source save.")
        if image.source in {"FILE", "GENERATED"} and not any(
                b["resource"] == f"image:{image.name}" for b in report["blockers"]):
            # Force lazy decoding/generation before packing. Packing arbitrary bytes
            # alone is not proof that Blender can use them as an image.
            pixels = image.pixels[:4]
            if len(pixels) != 4 or min(image.size) <= 0:
                block(report, "INVALID_DEPENDENCY", f"image:{image.name}", "Blender could not decode image pixels.")
    for font in list(bpy.data.fonts):
        dependency("font", font, builtin=font.filepath == "<builtin>")
        if font.filepath == "<builtin>" or any(b["resource"] == f"font:{font.name}" for b in report["blockers"]):
            continue
        # Blender may silently substitute its builtin font when a saved font's
        # bytes are corrupt. A fresh load forces format validation without reuse.
        probe = None
        try:
            with tempfile.TemporaryDirectory(prefix="msp-font-probe-") as temporary:
                path = Path(bpy.path.abspath(font.filepath, library=font.library))
                if font.packed_file:
                    path = Path(temporary) / "packed-font.ttf"
                    path.write_bytes(font.packed_file.data)
                probe = bpy.data.fonts.load(str(path), check_existing=False)
        except Exception as exc:
            block(report, "INVALID_DEPENDENCY", f"font:{font.name}", f"Blender could not load font bytes: {exc}")
        finally:
            if probe is not None:
                bpy.data.fonts.remove(probe)

    for kind in ("cache_files", "movieclips", "sounds", "volumes", "texts", "particles"):
        for item in getattr(bpy.data, kind):
            block(report, "UNSUPPORTED_DEPENDENCY", f"{kind}:{item.name}",
                  "Caches, media, embedded text/scripts and simulation data are outside the still-scene policy.")

    # Drivers can depend on Python namespaces/add-ons even with autoexec disabled.
    for item in datablocks:
        animation = getattr(item, "animation_data", None)
        if animation and animation.drivers:
            block(report, "UNSUPPORTED_DEPENDENCY", f"driver:{item.name}", "Driver evaluation is not allowed in a prepared static scene.")

    unsupported_modifiers = {"CLOTH", "SOFT_BODY", "FLUID", "DYNAMIC_PAINT", "PARTICLE_SYSTEM",
                             "PARTICLE_INSTANCE", "MESH_CACHE", "MESH_SEQUENCE_CACHE", "OCEAN", "NODES"}
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type in unsupported_modifiers:
                block(report, "UNSUPPORTED_DEPENDENCY", f"modifier:{obj.name}/{modifier.name}", f"Modifier {modifier.type} needs a separate deterministic/static proof.")
    for scene in bpy.data.scenes:
        if scene.rigidbody_world:
            block(report, "UNSUPPORTED_DEPENDENCY", f"scene:{scene.name}", "Rigid-body simulation is unsupported.")
        if scene.sequence_editor:
            strips = getattr(scene.sequence_editor, "strips_all", ())
            for strip in strips:
                block(report, "UNSUPPORTED_DEPENDENCY", f"strip:{scene.name}/{strip.name}", f"Sequencer strip {strip.type} is outside the still-scene policy.")
    for tree in node_trees(bpy):
        if tree.bl_idname == "GeometryNodeTree":
            block(report, "UNSUPPORTED_DEPENDENCY", f"node_tree:{tree.name}", "Geometry Nodes datablocks are outside the still-scene policy, including unused groups.")
        if tree.animation_data and tree.animation_data.drivers:
            block(report, "UNSUPPORTED_DEPENDENCY", f"driver:{tree.name}", "Node-tree drivers are outside the static-scene policy.")
        for node in tree.nodes:
            if node.bl_idname in {"ShaderNodeScript", "CompositorNodeOutputFile"}:
                block(report, "UNSUPPORTED_DEPENDENCY", f"node:{tree.name}/{node.name}", f"Node {node.bl_idname} needs external code or writes undeclared outputs.")
            image = getattr(node, "image", None)
            if node.bl_idname in {"ShaderNodeTexImage", "ShaderNodeTexEnvironment", "CompositorNodeImage"} and image is None:
                block(report, "MISSING_DEPENDENCY", f"node:{tree.name}/{node.name}", "Image input node has no assigned image.")
            if image is not None and image.source == "VIEWER":
                block(report, "UNSUPPORTED_DEPENDENCY", f"node:{tree.name}/{node.name}", "A transient viewer cannot serve as a saved input image.")

    # In the pinned 5.1 runtime, packed=True INCLUDES packed paths.
    # Older online API pages describe the opposite; verified with a packed fixture.
    paths = sorted({p for p in bpy.utils.blend_paths(absolute=True, packed=False, local=False) if p})
    report["remaining_external_paths"] = paths
    for path in paths:
        if os.path.normcase(str(Path(path).resolve())) not in known_paths:
            block(report, "UNSUPPORTED_DEPENDENCY", "unclassified_external_path", f"Unclassified Blender dependency: {path}")
    report["scene_summary"] = {
        "active_scene": bpy.context.scene.name,
        "scene_names": sorted(s.name for s in bpy.data.scenes),
        "object_count": len(bpy.data.objects),
        "mesh_count": len(bpy.data.meshes),
        "material_count": len(bpy.data.materials),
        "node_tree_count": len(node_trees(bpy)),
    }


def prepare_in_blender(args):
    import bpy

    source, output = Path(args.source).resolve(), Path(args.output_dir).resolve()
    report = new_report(source)
    started = time.monotonic()
    try:
        report["runtime"] = {
            "blender_version": bpy.app.version_string,
            "build_hash": bpy.app.build_hash.decode("ascii"),
            "autoexec_enabled": bpy.context.preferences.filepaths.use_scripts_auto_execute,
        }
        if (report["runtime"]["blender_version"] != PINNED_VERSION
                or report["runtime"]["build_hash"] != PINNED_BUILD):
            block(report, "RUNTIME_MISMATCH", "blender", f"Required {PINNED_VERSION} / {PINNED_BUILD}")
        if report["runtime"]["autoexec_enabled"]:
            block(report, "UNSUPPORTED_DEPENDENCY", "autoexec", "Automatic script execution must be disabled.")
        if not report["blockers"]:
            bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
            audit(bpy, report)
        if not report["blockers"]:
            # The operator emits supplemental diagnostics; explicit checks decide success.
            bpy.ops.file.report_missing_files()
            for image in bpy.data.images:
                if image.source == "FILE":
                    image.pack()
                    if not image.packed_file or not image.packed_file.size:
                        block(report, "MISSING_DEPENDENCY", f"image:{image.name}", "Packing produced no image bytes.")
            bpy.ops.file.pack_all()
            for font in bpy.data.fonts:
                if font.filepath != "<builtin>" and (not font.packed_file or not font.packed_file.size):
                    block(report, "MISSING_DEPENDENCY", f"font:{font.name}", "Packing produced no font bytes.")
            remaining = sorted({p for p in bpy.utils.blend_paths(absolute=True, packed=False, local=False) if p})
            report["remaining_external_paths"] = remaining
            if remaining:
                block(report, "UNSUPPORTED_DEPENDENCY", "post_pack", "External paths remain after packing.")
        if not report["blockers"]:
            prepared = output / "prepared.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(prepared), check_existing=False, relative_remap=True)
            if file_hash(source) != report["source"]["sha256"]:
                block(report, "HASH_MISMATCH", "source", "The original file changed during preparation.")
            else:
                report["prepared"] = {"path": str(prepared), "sha256": file_hash(prepared), "size_bytes": prepared.stat().st_size}
                report["status"] = "prepared"
    except Exception as exc:
        block(report, "BLENDER_FAILED", "preparation", f"{type(exc).__name__}: {exc}")
    report["elapsed_seconds"] = round(time.monotonic() - started, 6)
    write_report(output, report)
    # Blender can return zero on a normal script return; the host reads the report.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", required=True, help="New evidence directory; existing directories are rejected.")
    parser.add_argument("--blender-bin", default=os.environ.get("MSP_BLENDER_BIN") or shutil.which("blender"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--_in-blender", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args._in_blender:
        prepare_in_blender(args)
        return 0
    source, output = Path(args.source).resolve(), Path(args.output_dir).resolve()
    if args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("--timeout must be finite and positive")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("--output-dir must not already exist; choose a new evidence directory")
    report = new_report(source)
    started = time.monotonic()
    if not source.is_file():
        block(report, "MISSING_DEPENDENCY", "source", "Source .blend file does not exist.")
    elif source.suffix.lower() != ".blend":
        block(report, "UNSUPPORTED_DEPENDENCY", "source", "Preparation accepts .blend files only.")
    elif not args.blender_bin:
        block(report, "BLENDER_UNAVAILABLE", "runtime", "Set --blender-bin or MSP_BLENDER_BIN to the pinned Blender executable.")
    else:
        command = [args.blender_bin, "--background", "--factory-startup", "--disable-autoexec",
                   "--python-exit-code", "20", "--python", str(Path(__file__).resolve()), "--",
                   "--_in-blender", "--source", str(source), "--output-dir", str(output)]
        try:
            with (output / "blender.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            saved = output / "preparation-report.json"
            if saved.is_file():
                report = json.loads(saved.read_text(encoding="utf-8"))
            if result.returncode or not saved.is_file():
                block(report, "BLENDER_FAILED", "process", f"Blender exit={result.returncode}; see local blender.log.")
        except subprocess.TimeoutExpired:
            block(report, "PREPARATION_TIMEOUT", "process", f"Preparation exceeded {args.timeout} seconds.")
        except OSError as exc:
            block(report, "BLENDER_UNAVAILABLE", "process", str(exc))
    if report["blockers"]:
        report["status"], report["prepared"] = "blocked", None
    report["elapsed_seconds"] = round(time.monotonic() - started, 6)
    write_report(output, report)
    print(json.dumps({"status": report["status"], "report": str(output / "preparation-report.json"),
                      "blocker_codes": sorted({b["code"] for b in report["blockers"]})}))
    return 0 if report["status"] == "prepared" else 1


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    sys.exit(main(arguments))
