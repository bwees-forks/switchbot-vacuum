#!/usr/bin/env python3
"""Download one S10/S20 map package from S3 so the decoder can be checked against it.

The robot uploads its map to S3 as a directory of loose objects. The app reads
them from `{s3Object}/{mapID}/` — see docs/map-format.md. This walks the same
path the integration does:

    POST {auth}/account/api/v1/user/login              -> access token
    POST {auth}/account/api/v1/user/userinfo           -> botRegion
    POST {auth}/admin/admin/api/v1/botregion/endpoint  -> wonderlabs host
    POST {wonderlabs}/wonder/device/v3/getdevice       -> device list
    POST {wonderlabs}/device/device/v1/shadow/getByIDs -> map + S3 properties
    GET  s3://{bucket}/{s3Object}/{mapID}/*            -> the map package

Credentials are read from the environment and are only ever sent to SwitchBot:

    export SWITCHBOT_USERNAME='you@example.com'
    export SWITCHBOT_PASSWORD='...'
    python3 tools/dump_map.py

Requires boto3 (`pip install boto3`). Output lands in map_dump/, which is
gitignored — the files describe your home's floor plan, so do not commit them.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

API_AUTH_HOST = "https://account.api.switchbot.net"
CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
APP_VERSION = "8.6.1"
S3_REGION = "eu-central-1"
DEFAULT_S3_BUCKET = "prod-eu-sweeper-origin"
OUT_DIR = Path("map_dump")

PROP_MAP_ID = 1023
PROP_S3_BUCKET = 1028
PROP_S3_OBJECT = 1029
PROP_MAP_INFO = 1055
PROP_AWS_CREDS = 1130

MAP_FILES = (
    "refined_map.png",
    "refined_map.json",
    "mapinfo.json",
    "labels.json",
    "markers.json",
    "ai_objects.json",
    "track.json",
)

DEVICE_UUID = str(uuid.uuid4())


def post(url: str, payload: dict, token: str = "") -> dict:
    """POST JSON to the SwitchBot API and return the decoded body."""
    request = Request(
        url,
        data=json.dumps(payload).encode(),
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


def login() -> tuple[str, str]:
    """Return (token, wonderlabs_host)."""
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
                "deviceName": "map-dump",
                "model": "map-dump",
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
    endpoints = post(
        f"{API_AUTH_HOST}/admin/admin/api/v1/botregion/endpoint",
        {"botRegion": info.get("body", {}).get("botRegion")},
        token,
    )
    hosts = {e["name"]: e["host"] for e in endpoints.get("data", [])}
    if "wonderlabs" not in hosts:
        sys.exit(f"No 'wonderlabs' endpoint: {sorted(hosts)}")
    return token, hosts["wonderlabs"]


def pick_device(token: str, wonderlabs: str) -> str:
    """Return the MAC of the S10-family vacuum to dump."""
    data = post(
        f"{wonderlabs}/wonder/device/v3/getdevice",
        {"required_type": "All"},
        token,
    )
    candidates = [
        item
        for item in data.get("body", {}).get("Items", [])
        if item.get("device_detail", {}).get("device_type", "").startswith("WoSweeper")
        and "Mini" not in item.get("device_detail", {}).get("device_type", "")
    ]
    if not candidates:
        sys.exit("No S10-family vacuum in this account.")
    for item in candidates:
        print(f"  {item['device_mac']}  {item.get('device_name')}")
    return candidates[0]["device_mac"]


def properties(token: str, wonderlabs: str, mac: str) -> dict[int, object]:
    """Read the map and S3 properties from the device shadow."""
    data = post(
        f"{wonderlabs}/device/device/v1/shadow/getByIDs",
        {
            "deviceID": mac,
            "propertyIDs": [
                PROP_MAP_ID,
                PROP_S3_BUCKET,
                PROP_S3_OBJECT,
                PROP_MAP_INFO,
                PROP_AWS_CREDS,
            ],
        },
        token,
    )
    if data.get("resultCode") != 100:
        sys.exit(f"Property fetch failed: {data}")
    return {int(k): v.get("value") for k, v in (data.get("data") or {}).items()}


def main() -> None:
    """Dump every map object the robot has uploaded for its current map."""
    import boto3

    token, wonderlabs = login()
    mac = pick_device(token, wonderlabs)
    props = properties(token, wonderlabs, mac)

    creds = props.get(PROP_AWS_CREDS)
    prefix = props.get(PROP_S3_OBJECT)
    map_id = props.get(PROP_MAP_ID)
    bucket = props.get(PROP_S3_BUCKET) or DEFAULT_S3_BUCKET
    if not isinstance(creds, dict) or not prefix or not map_id:
        sys.exit(f"Device has no map yet (s3Object={prefix!r}, mapID={map_id!r})")

    print(f"\nbucket={bucket} prefix={prefix} mapID={map_id}")
    print(f"currentMapStatus (1055): {json.dumps(props.get(PROP_MAP_INFO), indent=2)}")

    s3 = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=creds["accessKeyId"],
        aws_secret_access_key=creds["secretAccessKey"],
        aws_session_token=creds["sessionToken"],
    )

    listing = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/{map_id}/")
    print("\nobjects under the map prefix:")
    for obj in listing.get("Contents", []):
        print(f"  {obj['Key']}  {obj['Size']:,} bytes")

    OUT_DIR.mkdir(exist_ok=True)
    names = [obj["Key"].rsplit("/", 1)[-1] for obj in listing.get("Contents", [])]
    for name in names or MAP_FILES:
        try:
            body = s3.get_object(Bucket=bucket, Key=f"{prefix}/{map_id}/{name}")["Body"].read()
        except Exception as exc:
            print(f"  skip {name}: {exc}")
            continue
        (OUT_DIR / name).write_bytes(body)
        print(f"  wrote {OUT_DIR / name} ({len(body):,} bytes)")

    metadata = OUT_DIR / "refined_map.json"
    if metadata.exists():
        print(f"\nrefined_map.json: {metadata.read_text()}")
    info = OUT_DIR / "mapinfo.json"
    if info.exists():
        print(f"mapinfo.json: {info.read_text()}")


if __name__ == "__main__":
    main()
