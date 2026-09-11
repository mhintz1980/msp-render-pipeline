"""Real Blender integration tests; a missing runtime is an error, never a skip."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msp_render_cli.cli import find_blender


FIXTURE_SCRIPT = r'''
import bpy
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[sys.argv.index("--") + 1])
for mode in ("complete", "missing", "packed", "sequence", "script", "generated", "corrupt", "appended", "linked", "node_driver", "unassigned", "strip", "unused_geometry", "font_complete", "font_corrupt", "font_packed"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    folder = root / mode
    folder.mkdir()
    bpy.ops.mesh.primitive_cube_add()
    if mode == "unused_geometry":
        tree = bpy.data.node_groups.new("UnusedGeometry", "GeometryNodeTree")
        tree.use_fake_user = True
    if mode.startswith("font_"):
        candidates = [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        original_font = next((p for p in candidates if p.is_file()), None)
        assert original_font, "A real test font is required"
        font_path = folder / "font.ttf"
        shutil.copyfile(original_font, font_path)
        bpy.ops.object.text_add()
        bpy.context.object.data.font = bpy.data.fonts.load(str(font_path))
        if mode == "font_packed":
            bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / "source.blend"))
        if mode == "font_corrupt":
            font_path.write_bytes(b"This is deliberately not a font")
        if mode == "font_packed":
            font_path.unlink()
        continue
    if mode in ("appended", "linked"):
        library = folder / "library.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(library))
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if mode == "appended":
            bpy.ops.wm.append(directory=str(library) + "/Object/", filename="Cube", do_reuse_local_id=True)
            assert any(item.library_weak_reference for item in bpy.data.meshes)
        else:
            with bpy.data.libraries.load(str(library), link=True) as (data_from, data_to):
                data_to.objects = ["Cube"]
            bpy.context.scene.collection.objects.link(data_to.objects[0])
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / "source.blend"))
        if mode == "appended":
            library.unlink()
        continue
    mat = bpy.data.materials.new("FixtureMaterial")
    mat.use_nodes = True
    bpy.context.object.data.materials.append(mat)
    image = bpy.data.images.new("FixtureTexture", width=2, height=2)
    image.generated_color = (0.25, 0.5, 0.75, 1.0)
    texture = folder / "texture.png"
    if mode != "generated":
        image.filepath_raw = str(texture)
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)
        image = bpy.data.images.load(str(texture))
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    mat.node_tree.links.new(node.outputs["Color"], mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])
    if mode == "unassigned":
        node.image = None
    if mode == "node_driver":
        curve = mat.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].driver_add("default_value")
        curve.driver.expression = "0.5"
    if mode == "strip":
        bpy.context.scene.sequence_editor_create().strips.new_image("FixtureStrip", str(texture), channel=1, frame_start=1)
    if mode == "packed":
        image.pack()
    if mode != "generated":
        image.filepath = "//texture.png"
    if mode == "sequence":
        image.source = "SEQUENCE"
    if mode == "script":
        code = bpy.data.texts.new("untrusted.py")
        code.write("raise RuntimeError('EMBEDDED_SCRIPT_EXECUTED')")
        code.use_module = True
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "source.blend"), relative_remap=False)
    if mode in ("missing", "packed"):
        texture.unlink()
    if mode == "corrupt":
        texture.write_bytes(b"This is deliberately not an image")
'''


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class TestScenePreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender = find_blender()
        cls.temp = tempfile.TemporaryDirectory(prefix="msp-scene-fixtures-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        builder = cls.root / "build_fixtures.py"
        builder.write_text(FIXTURE_SCRIPT, encoding="utf-8")
        result = subprocess.run(
            [cls.blender, "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "20", "--python", str(builder), "--", str(cls.root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def prepare(self, mode, output_name="prepared"):
        source = self.root / mode / "source.blend"
        before = sha256(source)
        output = self.root / mode / output_name
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/prepare_scene.py"), "--source", str(source),
             "--output-dir", str(output), "--blender-bin", self.blender],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        self.assertEqual(sha256(source), before, "The original scene must remain unchanged")
        report_path = output / "preparation-report.json"
        self.assertTrue(report_path.is_file(), result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "docs/prepared_scene.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(report)
        self.assertFalse(report["isolation_verified"])
        return result, report, output

    def test_missing_texture_is_a_typed_failure(self):
        result, report, output = self.prepare("missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("MISSING_DEPENDENCY", {b["code"] for b in report["blockers"]})
        self.assertIsNone(report["prepared"])
        self.assertFalse((output / "prepared.blend").exists())

    def test_complete_texture_is_packed_and_saved_hash_matches(self):
        result, report, output = self.prepare("complete")
        self.assertEqual(result.returncode, 0, json.dumps(report) + result.stdout + result.stderr)
        self.assertEqual(report["status"], "prepared")
        self.assertEqual(report["prepared"]["sha256"], sha256(output / "prepared.blend"))
        self.assertFalse(report["runtime"]["autoexec_enabled"])
        self.assertEqual(report["remaining_external_paths"], [])
        image = next(d for d in report["dependencies"] if d["kind"] == "image")
        self.assertEqual(image["storage"], "external")
        self.assertEqual(image["sha256"], sha256(self.root / "complete/texture.png"))

    def test_already_packed_texture_does_not_require_original_file(self):
        result, report, _ = self.prepare("packed")
        self.assertEqual(result.returncode, 0, json.dumps(report))
        self.assertEqual(report["dependencies"][0]["storage"], "packed")

    def test_generated_image_survives_reopen_with_its_saved_pixels(self):
        result, report, output = self.prepare("generated")
        self.assertEqual(result.returncode, 0, json.dumps(report))
        self.assertEqual(report["dependencies"][0]["storage"], "generated")
        expression = (
            "import bpy,json; "
            f"bpy.ops.wm.open_mainfile(filepath={str(self.root / 'generated/source.blend')!r}, use_scripts=False); "
            "original = list(bpy.data.images['FixtureTexture'].pixels[:4]); "
            f"bpy.ops.wm.open_mainfile(filepath={str(output / 'prepared.blend')!r}, use_scripts=False); "
            "print('PIXELS ' + json.dumps([original, list(bpy.data.images['FixtureTexture'].pixels[:4])]))"
        )
        reopened = subprocess.run(
            [self.blender, "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "20", "--python-expr", expression],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        self.assertEqual(reopened.returncode, 0, reopened.stdout + reopened.stderr)
        pixels = json.loads(next(line[7:] for line in reopened.stdout.splitlines() if line.startswith("PIXELS ")))
        self.assertEqual(len(pixels[0]), 4)
        self.assertEqual(pixels[0], pixels[1])

    def test_sequence_is_rejected_before_save(self):
        result, report, output = self.prepare("sequence")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNSUPPORTED_DEPENDENCY", {b["code"] for b in report["blockers"]})
        self.assertFalse((output / "prepared.blend").exists())

    def test_corrupt_image_cannot_pass_by_packing_arbitrary_bytes(self):
        result, report, output = self.prepare("corrupt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID_DEPENDENCY", {b["code"] for b in report["blockers"]})
        self.assertFalse((output / "prepared.blend").exists())

    def test_appended_provenance_is_recorded_and_cleared_in_prepared_copy(self):
        result, report, _ = self.prepare("appended")
        self.assertEqual(result.returncode, 0, json.dumps(report))
        self.assertTrue(report["sanitized_metadata"])
        self.assertTrue(all(r["original_path"].endswith("library.blend") for r in report["sanitized_metadata"]))
        self.assertEqual(report["remaining_external_paths"], [])

    def test_real_linked_library_is_not_mistaken_for_weak_metadata(self):
        result, report, output = self.prepare("linked")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(b["resource"].startswith("library:") for b in report["blockers"]))
        self.assertFalse((output / "prepared.blend").exists())

    def test_unassigned_image_node_is_a_missing_dependency(self):
        result, report, _ = self.prepare("unassigned")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(b["code"] == "MISSING_DEPENDENCY" and b["resource"].startswith("node:") for b in report["blockers"]))

    def test_embedded_node_tree_driver_is_rejected(self):
        result, report, _ = self.prepare("node_driver")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(b["resource"].startswith("driver:") for b in report["blockers"]))

    def test_unused_geometry_nodes_are_rejected(self):
        result, report, output = self.prepare("unused_geometry")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(b["resource"] == "node_tree:UnusedGeometry" for b in report["blockers"]))
        self.assertFalse((output / "prepared.blend").exists())

    def test_corrupt_font_is_rejected_before_silent_substitution(self):
        result, report, output = self.prepare("font_corrupt")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(b["code"] == "INVALID_DEPENDENCY" and b["resource"].startswith("font:") for b in report["blockers"]))
        self.assertFalse((output / "prepared.blend").exists())

    def test_complete_and_packed_fonts_are_supported(self):
        for mode in ("font_complete", "font_packed"):
            with self.subTest(mode=mode):
                result, report, _ = self.prepare(mode)
                self.assertEqual(result.returncode, 0, json.dumps(report))
                self.assertEqual(report["remaining_external_paths"], [])

    def test_sequencer_strip_is_rejected(self):
        result, report, _ = self.prepare("strip")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(b["resource"].startswith("strip:") for b in report["blockers"]))

    def test_embedded_script_is_rejected_without_execution(self):
        result, report, output = self.prepare("script")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(b["resource"] == "texts:untrusted.py" for b in report["blockers"]))
        self.assertNotIn("EMBEDDED_SCRIPT_EXECUTED", (output / "blender.log").read_text(encoding="utf-8"))

    def test_missing_runtime_is_explicit_and_evidence_cannot_be_reused(self):
        output = self.root / "missing-runtime"
        command = [sys.executable, str(ROOT / "scripts/prepare_scene.py"),
                   "--source", str(self.root / "complete/source.blend"), "--output-dir", str(output),
                   "--blender-bin", str(self.root / "no-such-blender.exe")]
        first = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(first.returncode, 1)
        report = json.loads((output / "preparation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["blockers"][0]["code"], "BLENDER_UNAVAILABLE")
        before = sha256(output / "preparation-report.json")
        second = subprocess.run(command, capture_output=True, timeout=15)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(before, sha256(output / "preparation-report.json"))


if __name__ == "__main__":
    unittest.main()
