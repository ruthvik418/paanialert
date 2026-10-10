"""Build the dashboard and publish it on AWS Amplify Hosting. Owner: C.

    python scripts/deploy_dashboard.py            # uses the AWS profile "paani"

What it does, creating anything that doesn't exist yet:
1. Amplify app "paanialert-dashboard" with branch "main", a rewrite so /public and /report work,
   and headers for the PWA files (manifest, service worker, Android assetlinks.json)
2. Amazon Location API key "paanialert-maps" for map tiles, limited to the app's URL and localhost
3. `npm run build` with the stack's API URL and the map key
4. Uploads dist/ as a manual deployment and waits until it's live

Later you can connect the GitHub repo in the Amplify console instead; this script
keeps working either way.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "dashboard"
APP_NAME = "paanialert-dashboard"
BRANCH = "main"
KEY_NAME = "paanialert-maps"
STACK = "paanialert"
PROFILE = os.environ.get("AWS_PROFILE", "paani")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

# Paths without a file extension (/report, /public) get index.html; real files are served as they are.
# html and webmanifest are listed so /offline.html and /manifest.webmanifest aren't rewritten,
# and /.well-known/assetlinks.json passes as json.
SPA_RULE = {
    "source": "</^[^.]+$|\\.(?!(css|gif|html|ico|jpg|jpeg|js|png|txt|svg|webmanifest|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>",
    "target": "/index.html",
    "status": "200",
}
# Android (PWABuilder / Trusted Web Activity) and Chrome's install check need these exact types,
# and a fresh service worker on every visit.
CUSTOM_HEADERS = """customHeaders:
  - pattern: '/manifest.webmanifest'
    headers:
      - key: 'Content-Type'
        value: 'application/manifest+json'
  - pattern: '/.well-known/assetlinks.json'
    headers:
      - key: 'Content-Type'
        value: 'application/json'
  - pattern: '/sw.js'
    headers:
      - key: 'Content-Type'
        value: 'text/javascript'
      - key: 'Cache-Control'
        value: 'no-cache'
"""


def main() -> None:
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    amplify = session.client("amplify")
    app_id = ensure_app(amplify)
    url = f"https://{BRANCH}.{app_id}.amplifyapp.com"
    map_key = ensure_map_key(session.client("location"), url)
    api_url = stack_output(session.client("cloudformation"), "ApiUrl")

    build(api_url, map_key)
    deploy(amplify, app_id)
    print(f"\nDashboard live: {url}\nPublic page:    {url}/public\nReport app:     {url}/report")


def ensure_app(amplify) -> str:
    apps = amplify.list_apps(maxResults=100)["apps"]
    app = next((a for a in apps if a["name"] == APP_NAME), None)
    if app is None:
        app = amplify.create_app(name=APP_NAME, platform="WEB", customRules=[SPA_RULE], customHeaders=CUSTOM_HEADERS)["app"]
        print(f"Created Amplify app {app['appId']}")
    elif app.get("customRules") != [SPA_RULE] or app.get("customHeaders") != CUSTOM_HEADERS:
        amplify.update_app(appId=app["appId"], customRules=[SPA_RULE], customHeaders=CUSTOM_HEADERS)
        print("Updated the Amplify rewrite rule and headers")
    branches = amplify.list_branches(appId=app["appId"])["branches"]
    if not any(b["branchName"] == BRANCH for b in branches):
        amplify.create_branch(appId=app["appId"], branchName=BRANCH, stage="PRODUCTION")
        print(f"Created branch {BRANCH}")
    return app["appId"]


def ensure_map_key(location, app_url: str) -> str:
    try:
        return location.describe_key(KeyName=KEY_NAME)["Key"]
    except location.exceptions.ResourceNotFoundException:
        pass
    location.create_key(
        KeyName=KEY_NAME,
        Description="Map tiles for the PaaniAlert dashboard",
        NoExpiry=True,
        Restrictions={
            "AllowActions": ["geo-maps:GetTile", "geo-maps:GetStaticMap"],
            "AllowResources": [f"arn:aws:geo-maps:{REGION}::provider/default"],
            "AllowReferers": [f"{app_url}/*", "http://localhost:5173/*"],
        },
    )
    print(f"Created Amazon Location key {KEY_NAME}")
    return location.describe_key(KeyName=KEY_NAME)["Key"]


def stack_output(cfn, key: str) -> str:
    outputs = cfn.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outputs if o["OutputKey"] == key)


def build(api_url: str, map_key: str) -> None:
    npm = shutil.which("npm") or "npm"
    env = dict(os.environ, VITE_API_URL=api_url, VITE_LOCATION_KEY=map_key, VITE_LOCATION_REGION=REGION)
    if not (DASHBOARD / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=DASHBOARD, check=True, shell=sys.platform == "win32")
    subprocess.run([npm, "run", "build"], cwd=DASHBOARD, env=env, check=True, shell=sys.platform == "win32")


def deploy(amplify, app_id: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in (DASHBOARD / "dist").rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(DASHBOARD / "dist").as_posix())
    job = amplify.create_deployment(appId=app_id, branchName=BRANCH)
    req = urllib.request.Request(job["zipUploadUrl"], data=buf.getvalue(), method="PUT",
                                 headers={"Content-Type": "application/zip"})
    urllib.request.urlopen(req, timeout=120).read()
    amplify.start_deployment(appId=app_id, branchName=BRANCH, jobId=job["jobId"])
    print(f"Deploying job {job['jobId']}", end="", flush=True)
    for _ in range(60):
        status = amplify.get_job(appId=app_id, branchName=BRANCH, jobId=job["jobId"])["job"]["summary"]["status"]
        if status in ("SUCCEED", "FAILED", "CANCELLED"):
            print(f" {status}")
            if status != "SUCCEED":
                sys.exit(f"Amplify deployment {status}")
            return
        print(".", end="", flush=True)
        time.sleep(5)
    sys.exit("Timed out waiting for Amplify")


if __name__ == "__main__":
    main()
