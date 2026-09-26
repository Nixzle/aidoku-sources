#!/usr/bin/env python3
"""Verify the public GitHub Pages catalog and critical AIX bytes after deployment."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import urllib.request
import zipfile
from urllib.parse import urljoin, urlparse

USER_AGENT = "Nixzle-Aidoku-Public-Acceptance/1.0"
MAX_JSON = 12 * 1024 * 1024
MAX_PACKAGE = 32 * 1024 * 1024
REQUIRED_MEMBERS = {"Payload/source.json", "Payload/main.wasm", "Payload/icon.png"}


def fetch(url: str, limit: int, attempts: int = 6) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError(f"unsafe public URL: {url}")
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise RuntimeError(f"response too large: {url}")
            return data
        except Exception as error:
            last = error
            if attempt + 1 < attempts:
                time.sleep(min(15, 2 ** attempt))
    raise RuntimeError(f"unable to fetch {url}: {last}")


def load_json(base: str, name: str) -> dict:
    value = json.loads(fetch(urljoin(base, name), MAX_JSON).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} is not a JSON object")
    return value


def verify_package(source: dict, inventory: dict, base: str) -> dict:
    source_id = source["id"]
    package_url = urljoin(base, source["downloadURL"])
    package = fetch(package_url, MAX_PACKAGE)
    digest = hashlib.sha256(package).hexdigest()
    if digest != inventory.get("sha256"):
        raise RuntimeError(f"{source_id}: public package checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = set(archive.namelist())
        if not REQUIRED_MEMBERS <= names:
            raise RuntimeError(f"{source_id}: public AIX is missing required members")
        manifest = json.loads(archive.read("Payload/source.json"))
    info = manifest.get("info", manifest)
    if info.get("id") != source_id or int(info.get("version", -1)) != int(source["version"]):
        raise RuntimeError(f"{source_id}: public AIX manifest does not match index")
    return {"id": source_id, "version": source["version"], "sha256": digest}


def run(base: str) -> dict:
    if not base.endswith("/"):
        base += "/"
    index = load_json(base, "index.min.json")
    inventory = load_json(base, "inventory.json")
    status = load_json(base, "status.json")
    sources = {item["id"]: item for item in index.get("sources", [])}
    inventory_sources = {item["id"]: item for item in inventory.get("sources", [])}
    required = status.get("requiredMaintainedSources", [])
    if not required:
        raise RuntimeError("public status has no required source set")
    verified = []
    for source_id in required:
        if source_id not in sources or source_id not in inventory_sources:
            raise RuntimeError(f"required source missing from public catalog: {source_id}")
        verified.append(verify_package(sources[source_id], inventory_sources[source_id], base))
    if int(inventory.get("sourceCount", -1)) != len(sources):
        raise RuntimeError("public inventory count does not match public index")
    return {"baseURL": base, "sourceCount": len(sources), "requiredPackages": verified}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://nixzle.github.io/aidoku-sources/")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.base_url), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
