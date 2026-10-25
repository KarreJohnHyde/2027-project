"""
Utility script to export Blender (.blend) files to WebGL / Three.js compatible GLB format.
Usage:
    python export_blend_to_glb.py Untitled.blend
    python export_blend_to_glb.py --all
"""

import sys
import os
import subprocess
from pathlib import Path

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
OUTPUT_DIR = Path(__file__).parent / "public" / "models"

# Inline script passed directly to Blender headless instance
BLENDER_INLINE_SCRIPT = """
import bpy
import sys

output_path = sys.argv[-1]
print(f"[Blender] Exporting scene objects ({len(bpy.data.objects)}) to: {output_path}")

# Export to GLB format (compact, binary glTF with materials and meshes)
bpy.ops.export_scene.gltf(
    filepath=output_path,
    export_format='GLB',
    use_selection=False,
    export_apply=True,
    export_cameras=True,
    export_lights=True
)
print("[Blender] Export successful!")
"""

def export_file(blend_path: Path):
    if not blend_path.exists():
        print(f"Error: File not found: {blend_path}")
        return False

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    glb_out = OUTPUT_DIR / f"{blend_path.stem}.glb"
    
    print(f"Converting '{blend_path.name}' -> '{glb_out.name}'...")
    
    cmd = [
        BLENDER_EXE,
        "--background",
        str(blend_path.resolve()),
        "--python-expr",
        BLENDER_INLINE_SCRIPT,
        "--",
        str(glb_out.resolve())
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        size_mb = round(glb_out.stat().st_size / (1024*1024), 2)
        print(f"[SUCCESS] Exported: {glb_out.name} ({size_mb} MB) -> {glb_out}")
        return True
    else:
        print(f"[FAILED] Failed to convert {blend_path.name}:")
        print(result.stderr or result.stdout)
        return False

def main():
    if not os.path.exists(BLENDER_EXE):
        print(f"Error: Blender executable not found at: {BLENDER_EXE}")
        sys.exit(1)

    args = sys.argv[1:]
    if not args or args[0] in ["--all", "-a"]:
        blend_files = list(Path(__file__).parent.glob("*.blend"))
        if not blend_files:
            print("No .blend files found in directory.")
            return
        print(f"Found {len(blend_files)} .blend file(s) to convert:")
        for bf in blend_files:
            export_file(bf)
    else:
        for arg in args:
            export_file(Path(arg))

if __name__ == "__main__":
    main()
