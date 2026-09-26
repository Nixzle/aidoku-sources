"""Explicit, monotonic client revisions for repaired same-version upstream packages.

Aidoku discovers source updates by integer version, not package checksum. Only
source IDs opted into policy are republished; their WASM and source IDs stay intact.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

TRANSFORM = "metadata-version-v1"
FIELDS = ("upstreamVersion", "upstreamSha256", "upstreamWasmSha256", "publicationTransform")


def validate_policy(policy: dict) -> set[str]:
    entries = policy.get("republishedSources", {})
    if not isinstance(entries, dict):
        raise ValueError("republishedSources must be an object")
    for source_id, detail in entries.items():
        if not isinstance(detail, dict):
            raise ValueError(f"Invalid republishing policy for {source_id}")
        minimum = detail.get("minimumPublishedVersion")
        if type(minimum) is not int or not 1 <= minimum < 2**31:
            raise ValueError("minimumPublishedVersion must be a positive 32-bit integer")
        reason = detail.get("reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("Republishing requires a bounded reason")
        if source_id in policy.get("localPackageOverrides", {}):
            raise ValueError("A source cannot use a local override and republishing together")
    return set(entries)


def repack_version(package: bytes, version: int) -> tuple[bytes, str]:
    """Change only the manifest version; preserve every other member's bytes."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as source:
        names = {name.casefold(): name for name in source.namelist()}
        manifest_name = names["payload/source.json"]
        wasm_digest = hashlib.sha256(source.read(names["payload/main.wasm"])).hexdigest()
        manifest = json.loads(source.read(manifest_name))
        info = manifest.get("info", manifest)
        info["version"] = version
        with zipfile.ZipFile(output, "w") as target:
            target.comment = source.comment
            for member in source.infolist():
                data = source.read(member.filename)
                if member.filename == manifest_name:
                    data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                target.writestr(member, data)
    return output.getvalue(), wasm_digest


def apply(candidates: list[dict], policy: dict, *, root: Path, updater) -> list[dict]:
    opted_in = validate_policy(policy)
    if not opted_in:
        return candidates
    _, previous = updater.load_current(root)
    result = []
    for candidate in candidates:
        source_id = candidate["id"]
        if source_id not in opted_in or candidate["repository"] != updater.ACTIVE_REPOSITORY:
            result.append(candidate)
            continue
        updater.validate_source_id(source_id)
        package = candidate["package"]
        upstream_digest = hashlib.sha256(package).hexdigest()
        old = previous.get(source_id, {})
        minimum = policy["republishedSources"][source_id]["minimumPublishedVersion"]
        upstream_version = candidate["version"]
        updater.read_package(package, source_id, expected_id=source_id, expected_version=upstream_version)
        known_revision = old.get("publicationTransform") == TRANSFORM
        # The normal updater's verified last-known-good cache is already republished.
        # Never increment it again during an upstream outage.
        if known_revision and upstream_digest == old.get("sha256"):
            if old["version"] != upstream_version:
                raise ValueError("Cached publication version is inconsistent")
            restored = dict(candidate)
            restored.update({key: old[key] for key in FIELDS})
            restored["upstreamPackageURL"] = old["upstreamPackageURL"]
            result.append(restored)
            continue
        if known_revision and old.get("upstreamSha256") == upstream_digest:
            if old.get("upstreamVersion") != upstream_version:
                raise ValueError("Upstream identity is inconsistent")
            version = max(minimum, old["version"])
        else:
            # Also handles a later upstream release colliding with our client version.
            version = max(minimum, upstream_version, int(old.get("version", 0)) + 1)
        if version >= 2**31:
            raise ValueError("Published source version exceeds the client integer range")
        revised, wasm_digest = repack_version(package, version)
        updater.read_package(revised, source_id, expected_id=source_id, expected_version=version)
        published = dict(candidate)
        published.update(version=version, package=revised, upstreamVersion=upstream_version,
                         upstreamSha256=upstream_digest, upstreamWasmSha256=wasm_digest,
                         publicationTransform=TRANSFORM)
        result.append(published)
        print(f"Published client revision {source_id} v{version} from upstream v{upstream_version}; WASM unchanged")
    return result


def validate_record(item: dict, package: bytes) -> None:
    present = any(key in item for key in FIELDS)
    if not present:
        return
    if item.get("publicationTransform") != TRANSFORM:
        raise ValueError("Unknown or incomplete package publication transform")
    original_version = item.get("upstreamVersion")
    if type(original_version) is not int or not 0 < original_version <= item["version"]:
        raise ValueError("Invalid original upstream version")
    for field in ("upstreamSha256", "upstreamWasmSha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get(field, ""))):
            raise ValueError("Invalid original package identity: " + field)
    if hashlib.sha256(package).hexdigest() != item.get("sha256"):
        raise ValueError("Published package checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = {name.casefold(): name for name in archive.namelist()}
        wasm = archive.read(names["payload/main.wasm"])
    if hashlib.sha256(wasm).hexdigest() != item["upstreamWasmSha256"]:
        raise ValueError("Republishing changed the recorded upstream WASM")
