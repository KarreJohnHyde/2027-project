"""
Blender scene inspection utility.
Can be executed either directly via:
    python inspect_blend.py Untitled.blend
    python inspect_blend.py --all
Or directly through Blender:
    blender -b Untitled.blend --python inspect_blend.py
"""

import sys
import os
import subprocess
from pathlib import Path

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

def run_inside_blender():
    import bpy
    print("\n" + "=" * 55)
    print(f"Blender File Inspection: {bpy.data.filepath}")
    print("=" * 55)
    print(f"Total Objects in Scene: {len(bpy.data.objects)}")
    print(f"Total Meshes:           {len(bpy.data.meshes)}")
    print(f"Total Materials:        {len(bpy.data.materials)}")
    print(f"Total Cameras:          {len(bpy.data.cameras)}")
    print(f"Total Lights:           {len(bpy.data.lights)}")
    print("-" * 55)
    
    print("Objects Summary:")
    for obj in bpy.data.objects:
        mesh_info = ""
        if obj.type == 'MESH' and obj.data:
            mesh_info = f" -> {len(obj.data.vertices):,} vertices, {len(obj.data.polygons):,} polygons"
        print(f" * [{obj.type:<7}] {obj.name}{mesh_info}")
    print("=" * 55 + "\n")

def run_from_python(blend_file: Path):
    if not blend_file.exists():
        print(f"Error: File not found: {blend_file}")
        return

    cmd = [
        BLENDER_EXE,
        "-b",
        str(blend_file.resolve()),
        "--python",
        str(Path(__file__).resolve()),
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True)
    in_block = False
    for line in proc.stdout.splitlines():
        if "Blender File Inspection:" in line:
            in_block = True
            print("=" * 55)
        if in_block:
            print(line)
            if "Blender 5.2" in line or "Blender quit" in line:
                break

def main():
    # If running inside Blender's embedded runtime
    if "bpy" in sys.modules or (len(sys.argv) > 0 and "blender" in sys.argv[0].lower()):
        try:
            import bpy
            if bpy.data.is_saved:
                run_inside_blender()
                return
        except ImportError:
            pass

    # If running from normal Python CLI
    args = sys.argv[1:]
    if not args or args[0] in ["--all", "-a"]:
        blend_files = list(Path(__file__).parent.glob("*.blend"))
        if not blend_files:
            print("No .blend files found in directory.")
            return
        for bf in blend_files:
            run_from_python(bf)
    else:
        for arg in args:
            run_from_python(Path(arg))

if __name__ == "__main__":
    main()
