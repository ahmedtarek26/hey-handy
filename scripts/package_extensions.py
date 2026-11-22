"""Build store-ready Chromium/Edge and Firefox/Zen MV3 extension ZIP packages."""

from __future__ import annotations

import argparse
import copy
import json
import zipfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "extension"

EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}


def _iter_extension_files(src_dir: Path) -> List[Path]:
    files: List[Path] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_NAMES or path.name.startswith("._"):
            continue
        if path.name == "manifest.json":
            continue
        files.append(path)
    return files


def build_store_manifest(base: dict, target: str) -> dict:
    """Create a store-clean MV3 manifest for 'chromium' (Chrome/Edge/Brave) or 'firefox' (AMO/Zen)."""
    manifest = copy.deepcopy(base)

    if target == "chromium":
        manifest["background"] = {"service_worker": "background.js"}
        manifest.pop("browser_specific_settings", None)
        return manifest

    if target == "firefox":
        manifest["background"] = {"scripts": ["background.js"]}
        manifest.pop("minimum_chrome_version", None)
        bss = manifest.setdefault("browser_specific_settings", {})
        gecko = bss.setdefault("gecko", {})
        gecko.setdefault("id", "hey-handy@ahmedtarek26.dev")
        # Mozilla AMO requires explicit data_collection_permissions on new MV3 add-ons (Nov 2025+).
        gecko["strict_min_version"] = "140.0"
        gecko["data_collection_permissions"] = {"required": ["none"]}
        return manifest

    raise ValueError(f"Unknown browser target: {target}")


def package_extensions(out_dir: Path, src_dir: Path = EXTENSION_DIR) -> Dict[str, Path]:
    """Generate store-ready ZIP archives with manifest.json at the archive root."""
    out_dir.mkdir(parents=True, exist_ok=True)
    base_manifest = json.loads((src_dir / "manifest.json").read_text(encoding="utf-8"))
    asset_files = _iter_extension_files(src_dir)

    outputs: Dict[str, Path] = {}
    targets = {
        "chromium": out_dir / "hey-handy-chromium-edge-mv3.zip",
        "firefox": out_dir / "hey-handy-firefox-zen-mv3.zip",
    }

    for target, zip_path in targets.items():
        store_manifest = build_store_manifest(base_manifest, target)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(store_manifest, indent=2) + "\n")
            for file_path in asset_files:
                arcname = file_path.relative_to(src_dir).as_posix()
                zf.write(file_path, arcname=arcname)
        outputs[target] = zip_path

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Hey Handy browser extensions for public stores.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist", help="Output directory for ZIP files.")
    args = parser.parse_args()

    built = package_extensions(args.out_dir)
    for target, path in built.items():
        print(f"Built {target}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
