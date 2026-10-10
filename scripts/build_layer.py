"""Build the Lambda dependencies layer into build/layer/python. Run before `sam build`.

Why not let SAM install requirements? SAM resolves dependencies on your own
machine, so on Windows it asks for Windows-only packages (mcp → pywin32) that
don't exist for Lambda's Linux. Here we resolve once, drop Windows-only
packages, and download Linux wheels explicitly. Works on Windows, macOS and Linux.

    python scripts/build_layer.py
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "layer" / "requirements.txt"
TARGET = ROOT / "build" / "layer" / "python"
WINDOWS_ONLY = {"pywin32", "pywin32-ctypes", "pywinpty"}
# Pure-Python packages published only as source (no wheel): built here instead. Never add a package with C code.
SOURCE_ONLY = {"http-ece"}   # needed by pywebpush
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


def remove(path: Path) -> None:
    """rmtree that also clears Windows read-only flags (OneDrive sets them)."""
    def clear_and_retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=clear_and_retry)


def main() -> None:
    pins = resolve()
    print(f"Resolved {len(pins)} packages")
    remove(TARGET.parent)
    TARGET.mkdir(parents=True)
    platform_args = [arg for p in PLATFORMS for arg in ("--platform", p)]
    is_source_only = lambda pin: pin.split("==")[0].lower().replace("_", "-") in SOURCE_ONLY
    pip("install", "--quiet", "--no-deps", "--only-binary=:all:", *platform_args,
        "--python-version", "3.12", "--implementation", "cp",
        "--target", str(TARGET), *[p for p in pins if not is_source_only(p)])
    source_only = [p for p in pins if is_source_only(p)]
    if source_only:   # pure Python, so building it here gives the same files Lambda would get
        pip("install", "--quiet", "--no-deps", "--target", str(TARGET), *source_only)
    (TARGET.parent / "pins.txt").write_text("\n".join(pins) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file()) / 1_048_576
    print(f"Layer ready: {TARGET} ({size:.0f} MB unzipped, Lambda allows 250 MB)")


if __name__ == "__main__":
    main()
