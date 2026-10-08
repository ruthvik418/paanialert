"""Build the Lambda dependencies layer into build/layer/python. Run before `sam build`.

Why not let SAM install requirements? SAM resolves dependencies on your own
machine, so on Windows it asks for Windows-only packages (mcp → pywin32) that
don't exist for Lambda's Linux. Here we resolve once, drop Windows-only
packages, and download Linux wheels explicitly. Works on Windows, macOS and Linux.

    python scripts/build_layer.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "layer" / "requirements.txt"
TARGET = ROOT / "build" / "layer" / "python"
WINDOWS_ONLY = {"pywin32", "pywin32-ctypes", "pywinpty"}
PLATFORMS = ["manylinux2014_x86_64", "manylinux_2_28_x86_64", "manylinux_2_17_x86_64"]


def pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", *args], check=True)


def resolve() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        pip("install", "--quiet", "--dry-run", "--ignore-installed",
            "--report", str(report), "-r", str(REQUIREMENTS))
        data = json.loads(report.read_text(encoding="utf-8"))
    pins = []
    for item in data["install"]:
        name, version = item["metadata"]["name"], item["metadata"]["version"]
        if name.lower() not in WINDOWS_ONLY:
            pins.append(f"{name}=={version}")
    return sorted(pins, key=str.lower)


def main() -> None:
    pins = resolve()
    print(f"Resolved {len(pins)} packages")
    if TARGET.parent.exists():
        shutil.rmtree(TARGET.parent)
    TARGET.mkdir(parents=True)
    platform_args = [arg for p in PLATFORMS for arg in ("--platform", p)]
    pip("install", "--quiet", "--no-deps", "--only-binary=:all:", *platform_args,
        "--python-version", "3.12", "--implementation", "cp",
        "--target", str(TARGET), *pins)
    (TARGET.parent / "pins.txt").write_text("\n".join(pins) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file()) / 1_048_576
    print(f"Layer ready: {TARGET} ({size:.0f} MB unzipped, Lambda allows 250 MB)")


if __name__ == "__main__":
    main()
