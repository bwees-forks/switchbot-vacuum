#!/usr/bin/env python3
"""Download the Sweeper React Native plugin bundle and mine it for the cloud API.

The S10/S20 control page is not in the APK — it is a React Native bundle fetched over
the air, which is why the drying and dust-collection function IDs are still unknown.
This walks the same hot-update API the app uses:

    POST {publish}/publishplatform/api/v1/rn/plugin          -> installed plugin list
    POST {publish}/publishplatform/api/v1/rn/plugIn/downloadUrl -> signed bundle URL
    GET  {downloadUrl}                                       -> bundle.zip

Credentials are read from the environment and are only ever sent to SwitchBot:

    export SWITCHBOT_USERNAME='you@example.com'
    export SWITCHBOT_PASSWORD='...'
    python3 tools/fetch_rn_bundle.py

Endpoints and payload shapes were read from HotUpdateApiService, RnPlugReq,
RnDownloadUrlReq and RnDownloadResp in the 10.1 APK.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

API_AUTH_HOST = "https://account.api.switchbot.net"
CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
APP_VERSION = "10.1"
# The plugin list keys on the RN appId ("Sweeper"), not the module name
# ("com.switch.bot.sweeper") used to route to the page.
PLUGIN_NAME = "Sweeper"
OUT_DIR = Path("rn_bundle")

DEVICE_UUID = str(uuid.uuid4())


def post(url: str, payload: dict, token: str = "") -> dict:
    """POST JSON to the SwitchBot API and return the decoded body."""
    body = json.dumps(payload).encode()
    request = Request(
        url,
        data=body,
        headers={
            "authorization": token,
            "uuid": DEVICE_UUID,
            "requestid": str(uuid.uuid4()),
            "appversion": APP_VERSION,
            "content-type": "application/json; charset=UTF-8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def login() -> tuple[str, str, str]:
    """Return (token, user_id, publish_host)."""
    username = os.environ.get("SWITCHBOT_USERNAME")
    password = os.environ.get("SWITCHBOT_PASSWORD")
    if not username or not password:
        sys.exit("Set SWITCHBOT_USERNAME and SWITCHBOT_PASSWORD first.")

    data = post(
        f"{API_AUTH_HOST}/account/api/v1/user/login",
        {
            "clientId": CLIENT_ID,
            "deviceInfo": {
                "deviceId": DEVICE_UUID,
                "deviceName": "bundle-fetch",
                "model": "bundle-fetch",
            },
            "grantType": "password",
            "password": password,
            "username": username,
            "verifyCode": "",
        },
    )
    token = data.get("body", {}).get("access_token")
    if not token:
        sys.exit(f"Login failed: {data.get('message', data)}")

    info = post(f"{API_AUTH_HOST}/account/api/v1/user/userinfo", {}, token)
    user_id = info.get("body", {}).get("userID", "")
    bot_region = info.get("body", {}).get("botRegion")

    endpoints = post(
        f"{API_AUTH_HOST}/admin/admin/api/v1/botregion/endpoint",
        {"botRegion": bot_region},
        token,
    )
    hosts = {e["name"]: e["host"] for e in endpoints.get("data", [])}
    print(f"endpoints: {sorted(hosts)}")
    publish = hosts.get("publish")
    if not publish:
        sys.exit(f"No 'publish' endpoint for region {bot_region}: {hosts}")
    return token, user_id, publish


def fetch_bundle(token: str, user_id: str, publish: str) -> bytes:
    """Resolve the sweeper plugin version and download its bundle."""
    plugins = post(
        f"{publish}/publishplatform/api/v1/rn/plugin",
        {"appVersion": APP_VERSION, "userID": user_id, "platform": "android"},
        token,
    )
    rn_list = (plugins.get("data") or plugins.get("body") or {}).get("rnList", [])
    for plugin in rn_list:
        print(f"  {plugin.get('rnPluginName')} {plugin.get('rnPluginVersion')}")

    match = next(
        (p for p in rn_list if p.get("rnPluginName") == PLUGIN_NAME),
        None,
    )
    if not match:
        sys.exit(f"{PLUGIN_NAME} not offered to this account. Listed above.")

    version = match["rnPluginVersion"]
    print(f"\n{PLUGIN_NAME} version {version}")

    resp = post(
        f"{publish}/publishplatform/api/v1/rn/plugIn/downloadUrl",
        {
            "rnPluginName": PLUGIN_NAME,
            "rnPluginVersion": version,
            "platform": "android",
        },
        token,
    )
    url = (resp.get("data") or resp.get("body") or {}).get("downloadUrl")
    if not url:
        sys.exit(f"No downloadUrl in response: {resp}")

    print(f"downloading {url}")
    with urlopen(url, timeout=120) as response:
        return response.read()


# Function IDs the integration already knows, to separate old from new.
KNOWN_IDS = {1001: "clean", 1009: "control", 1022: "go_charge", 1043: "change_mode"}


def mine(bundle: str) -> None:
    """Report the command surface found in the bundle."""
    ids: dict[str, set[str]] = {}
    # The app calls invokeFunc with a numeric functionID; capture nearby context.
    for match in re.finditer(r"functionID\s*[:=]\s*(\d{3,5})", bundle):
        ids.setdefault(match.group(1), set()).add(
            bundle[max(0, match.start() - 120) : match.start() + 120]
        )

    print("\n=== functionID occurrences ===")
    for fid in sorted(ids, key=int):
        known = KNOWN_IDS.get(int(fid), "NEW")
        print(f"  {fid}  [{known}]")

    print("\n=== candidate command names ===")
    names = sorted(
        set(
            re.findall(
                r"['\"](start_drying|start_dust_collection|dust_collection|drying|"
                r"add_water|collect_dust|wash_mop|clean_all|clean_rooms|stop|pause)['\"]",
                bundle,
            )
        )
    )
    print("  " + ", ".join(names) if names else "  none")

    print("\n=== API paths ===")
    for path in sorted(
        set(re.findall(r"/(?:wonder|command|device|sweeper)[a-zA-Z0-9/_.-]+", bundle))
    ):
        print(f"  {path}")

    print("\n=== segment / room references ===")
    hits = sorted(
        set(
            re.findall(
                r"['\"]([a-zA-Z_]*(?:room|segment|area|zone)[a-zA-Z_]*)['\"]",
                bundle,
                re.IGNORECASE,
            )
        )
    )
    print("  " + ", ".join(hits[:60]) if hits else "  none")


def main() -> None:
    """Fetch the bundle, unpack it and report what it reveals."""
    token, user_id, publish = login()
    zip_bytes = fetch_bundle(token, user_id, publish)

    OUT_DIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        archive.extractall(OUT_DIR)
        print(f"\nextracted to {OUT_DIR}/: {archive.namelist()[:10]}")

    # The published artifact wraps the real payload in a second bundle.zip.
    for nested in list(OUT_DIR.rglob("*.zip")):
        target = nested.with_suffix("")
        with zipfile.ZipFile(nested) as archive:
            archive.extractall(target)
            print(f"unpacked {nested.name} -> {target.name}/: {archive.namelist()[:10]}")

    bundles = [
        p
        for pattern in ("*.bundle", "*.js", "*.hbc", "*.jsbundle")
        for p in OUT_DIR.rglob(pattern)
    ]
    if not bundles:
        sys.exit(f"No JS bundle inside. Contents: {list(OUT_DIR.rglob('*'))}")

    biggest = max(bundles, key=lambda p: p.stat().st_size)
    print(f"mining {biggest} ({biggest.stat().st_size:,} bytes)")
    mine(biggest.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    main()
