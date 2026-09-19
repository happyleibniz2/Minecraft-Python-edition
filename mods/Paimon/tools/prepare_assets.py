from pathlib import Path
import sys

REQUIRED = (
    "paimon_body.png",
    "paimon_face.png",
    "paimon_hair.png",
    "paimon_cloak.png",
    "paimon.obj",
)

ASSETS_DIR = (Path(__file__).resolve().parents[1] / "assets").resolve()
missing = [name for name in REQUIRED if not (ASSETS_DIR / name).is_file()]

if missing:
    print("Missing required asset files:")
    for name in missing:
        print(f"  - {name}")
    print(f"Place them in: {ASSETS_DIR}")
    print("Expected filenames: " + ", ".join(REQUIRED))
    raise SystemExit(1)

print("All required assets are present.")
print(f"Asset directory: {ASSETS_DIR}")
raise SystemExit(0)
