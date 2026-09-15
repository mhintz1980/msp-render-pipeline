"""Blender regression coverage for shadow-catcher construction and cleanup."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path(os.environ.get("MSP_BLENDER_BIN")
               or r"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")


DRIVER = r'''
import json
import os
import sys
from pathlib import Path

import bpy
import mathutils

repo = Path(os.environ["MSP_REPO"])
work = Path(os.environ["MSP_WORK"])
sys.path.insert(0, str(repo))
import render_worker


def catcher_checks(obj):
    assert obj is not None, "GroundShadowCatcher was not created"
    assert obj.type == "MESH"
    assert obj.is_shadow_catcher is True
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission",
                 "visible_volume_scatter"):
        assert getattr(obj, attr) is False, f"{attr} remained enabled"
    return True


# Exercise setup_lighting's ordinary (non-preserve-existing) branch.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.object.camera_add(location=(3.0, -3.0, 2.0))
camera = bpy.context.object
camera.name = "SetupCamera"
bpy.context.scene.camera = camera
render_worker.setup_lighting(
    {"preset": "studio_dark", "shadow_catcher": True, "analytic_lights": False},
    mathutils.Vector((0.0, 0.0, 0.5)),
    1.0,
)
normal_catcher = bpy.data.objects.get("GroundShadowCatcher")
catcher_checks(normal_catcher)
normal_catcher_name = normal_catcher.name
assert bpy.context.scene.camera is camera, "setup_lighting changed the active camera"

# The disabled setting must remove a catcher left by the prior setup.
render_worker.setup_lighting(
    {"preset": "studio_dark", "shadow_catcher": False, "analytic_lights": False},
    mathutils.Vector((0.0, 0.0, 0.5)),
    1.0,
)
assert bpy.data.objects.get("GroundShadowCatcher") is None


# Build a tiny native scene, then execute the real preserve-existing path.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.5))
cube = bpy.context.object
cube.name = "SyntheticProduct"
bpy.ops.object.camera_add(location=(3.0, -3.0, 2.0))
scene_camera = bpy.context.object
scene_camera.name = "SceneCamera"
scene_camera.rotation_euler = (mathutils.Vector((0.0, 0.0, 0.5)) - scene_camera.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = scene_camera
bpy.ops.object.light_add(type="AREA", location=(2.0, -2.0, 3.0))
bpy.context.object.name = "ExistingKey"
bpy.context.object.data.energy = 100.0
source = work / "synthetic.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(source))

render_worker.write_matte_pass = lambda output_dir: print("MATTE_WRITER_STUB")
manifest = {
    "job_id": "shadow-catcher-regression",
    "cad_source": {"file_path": str(source), "format": "blend"},
    "camera": {"preset": "PRESERVE_EXISTING"},
    "livery": {"preset": "preserve_existing"},
    "lighting": {"preset": "preserve_existing", "shadow_catcher": True},
    "photoreal": {"enabled": False},
    "output": {
        "engine": "BLENDER_WORKBENCH",
        "width": 8,
        "height": 8,
        "passes": {"alpha_mask": True},
        "output_dir": str(work / "output"),
    },
}
render_worker.execute_render_job(manifest)
preserved_catcher = bpy.data.objects.get("GroundShadowCatcher")
catcher_checks(preserved_catcher)
preserved_catcher_name = preserved_catcher.name
assert bpy.context.scene.camera is not None
assert bpy.context.scene.camera.name == "SceneCamera", "preserve-existing camera was not retained"
assert bpy.data.objects.get("SceneCamera").hide_render is False

print(json.dumps({
    "checks": [
        "setup_lighting creates muted shadow catcher",
        "shadow_catcher false removes existing catcher",
        "execute_render_job preserve_existing creates muted shadow catcher",
        "preserve_existing retains active camera",
    ],
    "normal_catcher": normal_catcher_name,
    "preserved_catcher": preserved_catcher_name,
}))
'''


class TestShadowCatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BLENDER.is_file():
            raise AssertionError(f"Pinned Blender executable unavailable: {BLENDER}")

    def test_shadow_catcher_setup_execute_and_disable(self):
        with tempfile.TemporaryDirectory(prefix="msp-shadow-catcher-") as tmp:
            work = Path(tmp)
            driver = work / "shadow_catcher_driver.py"
            driver.write_text(textwrap.dedent(DRIVER), encoding="utf-8")
            env = dict(os.environ, MSP_REPO=str(ROOT), MSP_WORK=str(work))
            result = subprocess.run(
                [str(BLENDER), "--background", "--factory-startup", "--disable-autoexec",
                 "--python-exit-code", "20", "--python", str(driver)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env=env,
            )
            self.assertEqual(result.returncode, 0,
                             msg=f"Blender fixture failed:\n{result.stdout}\n{result.stderr}")
            self.assertIn("MATTE_WRITER_STUB", result.stdout)
            records = [line for line in result.stdout.splitlines() if line.startswith("{")]
            self.assertTrue(records, result.stdout)
            report = json.loads(records[-1])
            self.assertEqual(len(report["checks"]), 4)
            self.assertEqual(report["normal_catcher"], "GroundShadowCatcher")
            self.assertEqual(report["preserved_catcher"], "GroundShadowCatcher")


if __name__ == "__main__":
    unittest.main()
