#!/usr/bin/env python3
"""Verify the bytes Aidoku receives against a pinned Git snapshot, not a mutable branch."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit, unquote

try:
    from scripts import update_sources as updater
except ModuleNotFoundError:
    import update_sources as updater

BASE_URL = "https://nixzle.github.io/aidoku-sources/"
TEXT_FILES = ("index.min.json", "index.json", "inventory.json", "CHECKSUMS.sha256",
              "legacy/index.min.json", "legacy/index.json", "legacy/inventory.json",
              "legacy/CHECKSUMS.sha256", "status.json", "status.md",
              "config/source_policy.json", "config/source_health.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ValueError("Invalid artifact path")
    parsed = urlsplit(value)
    decoded = unquote(value)
    path = PurePosixPath(decoded)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or path.is_absolute()
            or "\\" in decoded or ":" in decoded or any(p in ("..", ".") for p in decoded.split("/"))
            or any(ord(c) < 32 for c in decoded) or str(path) != value):
        raise ValueError("Unsafe artifact path")
    return value


def git_bytes(root: Path, commit: str, path: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected commit must be a full 40-character SHA")
    relative_path(path)
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root,
                          check=True, capture_output=True, timeout=15).stdout


def fetch(path: str, base_url: str = BASE_URL) -> bytes:
    relative_path(path)
    if base_url != BASE_URL:
        raise ValueError("Only the configured public feed may be verified")
    maximum = updater.MAX_PACKAGE_BYTES if path.endswith(".aix") else updater.MAX_INDEX_BYTES
    return updater.fetch_bytes(urljoin(base_url, path), allowed_hosts={"nixzle.github.io"},
                               maximum=maximum, attempts=2, timeout=15)


def check_manifests(expected: dict[str, bytes], received: dict[str, bytes]) -> list[dict]:
    result = []
    for path, content in expected.items():
        if received.get(path) != content:
            raise ValueError(f"Public snapshot mismatch: {path}")
        result.append({"path": path, "sha256": digest(content)})
    return result


def catalog_assets(index_bytes: bytes, inventory_bytes: bytes, prefix="") -> list[dict]:
    index = json.loads(index_bytes)
    inventory = json.loads(inventory_bytes)
    entries = index["sources"]
    items = inventory["sources"]
    if not isinstance(entries, list) or not entries or len(entries) != inventory["sourceCount"]:
        raise ValueError("Invalid or empty catalog")
    ids = [entry["id"] for entry in entries]
    inventory_ids = [entry["id"] for entry in items]
    if len(ids) != len(set(ids)) or len(inventory_ids) != len(set(inventory_ids)) or set(ids) != set(inventory_ids):
        raise ValueError("Duplicate or inconsistent source IDs")
    by_id = {entry["id"]: entry for entry in items}
    result = []
    for entry in entries:
        updater.validate_source_id(entry["id"])
        item = by_id[entry["id"]]
        if entry["version"] != item["version"] or entry["downloadURL"] != item["file"]:
            raise ValueError("Catalog and inventory disagree")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise ValueError("Missing package checksum")
        result.append({"id": entry["id"], "version": entry["version"], "sha256": item["sha256"],
                       "path": prefix + relative_path(entry["downloadURL"]),
                       "icon": prefix + relative_path(entry["iconURL"])})
    return result


def verify_package(asset: dict, package: bytes, icon: bytes) -> dict:
    if digest(package) != asset["sha256"]:
        raise ValueError(f"Public package hash mismatch: {asset['id']}")
    _, embedded_icon = updater.read_package(package, asset["id"], expected_id=asset["id"],
                                           expected_version=asset["version"])
    if icon != embedded_icon:
        raise ValueError(f"Public icon differs from its package: {asset['id']}")
    return {"id": asset["id"], "version": asset["version"], "path": asset["path"],
            "sha256": asset["sha256"], "iconSha256": digest(icon)}


def verify(root: Path, commit: str, *, attempts=6, retry_seconds=15) -> tuple[dict, dict[str, bytes]]:
    expected = {path: git_bytes(root, commit, path) for path in TEXT_FILES}
    received = {}
    manifests = []
    for attempt in range(attempts):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                received = dict(zip(TEXT_FILES, executor.map(fetch, TEXT_FILES)))
            manifests = check_manifests(expected, received)
            break
        except (RuntimeError, ValueError) as error:
            if attempt + 1 == attempts:
                raise
            print(f"Waiting for the expected Pages snapshot ({attempt + 1}/{attempts}): {error}")
            time.sleep(retry_seconds)
    assets = []
    for prefix in ("", "legacy/"):
        assets.extend(catalog_assets(received[prefix + "index.min.json"], received[prefix + "inventory.json"], prefix))
    policy = json.loads(received["config/source_policy.json"])
    maintained = {item["id"] for item in assets if not item["path"].startswith("legacy/")}
    if set(policy["requiredMaintainedSources"]) - maintained:
        raise ValueError("Required maintained sources are absent from the live feed")
    def download(asset):
        package, icon = fetch(asset["path"]), fetch(asset["icon"])
        return asset, package, icon, verify_package(asset, package, icon)
    packages = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for asset, package, icon, result in executor.map(download, assets):
            received[asset["path"]] = package
            received[asset["icon"]] = icon
            packages.append(result)
    # Detect a deployment changing halfway through the download pass.
    for path in ("index.min.json", "inventory.json", "legacy/index.min.json", "status.json"):
        if fetch(path) != expected[path]:
            raise ValueError("Public deployment changed during acceptance; re-run against the new commit")
    report = {"schema": "AIDOKU_PUBLIC_ACCEPTANCE_V1", "status": "passed", "expectedCommit": commit,
              "checkedAt": updater.source_health.utc_now(), "baseURL": BASE_URL,
              "scope": "Public feeds, package metadata, package bytes and icons. Not chapter reading.",
              "manifests": manifests, "packages": sorted(packages, key=lambda p: p["path"]),
              "packageCount": len(packages)}
    return report, received


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, default=Path("acceptance/public.json"))
    parser.add_argument("--attempts", type=int, default=6, choices=range(1, 9))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report, verified = verify(args.root, args.expected_commit, attempts=args.attempts)
        bundle = args.output.with_suffix(".known-good.zip")
        # One complete known-good distribution, tied to the exact receipt and commit.
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(verified.items()):
                archive.writestr(path, data)
            archive.writestr("acceptance-receipt.json", json.dumps(report, indent=2))
        report["recoveryBundleSha256"] = digest(bundle.read_bytes())
        code = 0
    except Exception as error:
        report = {"schema": "AIDOKU_PUBLIC_ACCEPTANCE_V1", "status": "failed",
                  "expectedCommit": args.expected_commit, "checkedAt": updater.source_health.utc_now(),
                  "error": str(error)[:1500]}
        code = 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("manifests", "packages")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
