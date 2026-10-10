"""Build and deploy the backend in one step. Owner: A.

    python scripts/deploy_backend.py

Builds the dependency layer if it's missing, runs `sam build` into a folder in
your home directory (OneDrive and similar sync tools lock files inside the repo
and break the build), then `sam deploy` with the repo's samconfig.toml.
Pass --layer to rebuild the layer after changing layer/requirements.txt.
Pass --stack-name NAME to deploy a separate copy (e.g. paanialert-test) instead of
samconfig.toml's stack; it uses the same SSM parameters and stack settings.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path.home() / ".paanialert-build"


def sam() -> str:
    found = shutil.which("sam") or shutil.which("sam.cmd")
    if found:
        return found
    default = Path(r"C:\Program Files\Amazon\AWSSAMCLI\bin\sam.cmd")
    if default.exists():
        return str(default)
    sys.exit("AWS SAM CLI not found. Install it first (see README).")


def remove(path: Path) -> None:
    """rmtree that also clears Windows read-only flags (copied over from OneDrive folders)."""
    def clear_and_retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=clear_and_retry)


def run(*cmd: str) -> None:
    subprocess.run(list(cmd), cwd=ROOT, check=True, shell=sys.platform == "win32" and cmd[0].lower().endswith(".cmd"))


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        sys.exit("Run this with Python 3.12 (Lambda's version), e.g. `py -3.12 scripts/deploy_backend.py` "
                 "or from the project's .venv.")
    if "--layer" in sys.argv or not (ROOT / "build" / "layer" / "python").exists():
        run(sys.executable, str(ROOT / "scripts" / "build_layer.py"))
    remove(ROOT / ".aws-sam")
    remove(BUILD / "sam")
    # sam build needs a Python 3.12 on PATH; the one running this script is put first.
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    run(sam(), "build", "--build-dir", str(BUILD / "sam"), "--cache-dir", str(BUILD / "cache"))
    stack = sys.argv[sys.argv.index("--stack-name") + 1] if "--stack-name" in sys.argv else None
    run(sam(), "deploy", "--template-file", str(BUILD / "sam" / "template.yaml"),
        "--config-file", str(ROOT / "samconfig.toml"), "--no-progressbar",
        *(["--stack-name", stack] if stack else []))


if __name__ == "__main__":
    main()
