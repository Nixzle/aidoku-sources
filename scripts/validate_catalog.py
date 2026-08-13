#!/usr/bin/env python3
"""Validate the published Aidoku catalogs and every referenced package.

This script is intentionally dependency-free so it can run both in GitHub
Actions and on a fresh local checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID_PATTERN = re.compile(r"(?:en|multi)\.[a-z0-9][a-z0-9._-]*\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
ENGLISH_MARKERS = {"en", "all", "multi"}
MAX_ARCHIVE_ENTRIES = 128
MAX_ARCHIVE_COMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_PUBLISHED_ICON_BYTES = 8 * 1024 * 1024
REQUIRED_AIX_MEMBERS = {
    "Payload/source.json",
    "Payload/icon.png",
    "Payload/main.wasm",
}


class ValidationFailure(Exception):
    """A catalog failed one or more integrity checks."""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        raise ValidationFailure(f"missing required file: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationFailure(f"cannot parse JSON file {path}: {error}") from error


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def safe_relative_path(value: object, field: str, expected_directory: str) -> PurePosixPath:
    require(isinstance(value, str) and bool(value), f"{field} must be a non-empty string")
    parsed = urlsplit(value)
    require(
        not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment,
        f"{field} must be a plain relative path: {value!r}",
    )
    require("\\" not in value, f"{field} must use forward slashes: {value!r}")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{field} must not be absolute: {value!r}")
    require(
        all(part not in {"", ".", ".."} for part in path.parts),
        f"{field} contains an unsafe path component: {value!r}",
    )
    require(
        len(path.parts) == 2 and path.parts[0] == expected_directory,
        f"{field} must point directly inside {expected_directory}/: {value!r}",
    )
    return path


def validate_source_entry(entry: object, catalog_name: str) -> tuple[str, PurePosixPath, PurePosixPath]:
    require(isinstance(entry, dict), f"{catalog_name}: every source entry must be an object")

    source_id = entry.get("id")
    require(
        isinstance(source_id, str) and SOURCE_ID_PATTERN.fullmatch(source_id) is not None,
        f"{catalog_name}: invalid English/multilingual source id: {source_id!r}",
    )
    name = entry.get("name")
    require(
        isinstance(name, str) and bool(name.strip()),
        f"{catalog_name}: {source_id} has no display name",
    )
    version = entry.get("version")
    require(
        isinstance(version, int) and not isinstance(version, bool) and version >= 1,
        f"{catalog_name}: {source_id} has invalid version {version!r}",
    )
    languages = entry.get("languages")
    require(
        isinstance(languages, list)
        and all(isinstance(language, str) for language in languages)
        and any(language.casefold() in ENGLISH_MARKERS for language in languages),
        f"{catalog_name}: {source_id} is not marked English or multilingual",
    )
    content_rating = entry.get("contentRating")
    require(
        isinstance(content_rating, int)
        and not isinstance(content_rating, bool)
        and content_rating in {0, 1, 2},
        f"{catalog_name}: {source_id} has invalid contentRating {content_rating!r}",
    )
    base_url = entry.get("baseURL")
    parsed_base_url = urlsplit(base_url) if isinstance(base_url, str) else None
    require(
        parsed_base_url is not None
        and parsed_base_url.scheme == "https"
        and bool(parsed_base_url.netloc)
        and not parsed_base_url.username
        and not parsed_base_url.password,
        f"{catalog_name}: {source_id} has an unsafe baseURL {base_url!r}",
    )

    package_path = safe_relative_path(entry.get("downloadURL"), "downloadURL", "sources")
    icon_path = safe_relative_path(entry.get("iconURL"), "iconURL", "icons")
    expected_stem = f"{source_id}-v{version}"
    require(
        package_path.name == f"{expected_stem}.aix",
        f"{catalog_name}: {source_id} package filename does not match its id/version",
    )
    require(
        icon_path.name == f"{expected_stem}.png",
        f"{catalog_name}: {source_id} icon filename does not match its id/version",
    )
    return source_id, package_path, icon_path


def validate_archive_member(name: str, source_id: str) -> None:
    require("\\" not in name, f"{source_id}: archive member uses backslashes: {name!r}")
    path = PurePosixPath(name)
    require(
        not path.is_absolute()
        and bool(path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"{source_id}: unsafe archive member path: {name!r}",
    )


def validate_aix(path: Path, entry: dict, catalog_name: str) -> str:
    source_id = entry["id"]
    require(
        path.is_file() and not path.is_symlink(),
        f"{catalog_name}: missing or unsafe package for {source_id}: {path}",
    )
    require(
        path.stat().st_size <= MAX_ARCHIVE_COMPRESSED_BYTES,
        f"{catalog_name}: {source_id} package is too large",
    )
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            require(
                len(members) <= MAX_ARCHIVE_ENTRIES,
                f"{catalog_name}: {source_id} contains too many archive members",
            )
            names: set[str] = set()
            casefolded_names: dict[str, str] = {}
            total_size = 0
            for member in members:
                validate_archive_member(member.filename, source_id)
                require(
                    member.filename not in names,
                    f"{catalog_name}: {source_id} contains duplicate archive member {member.filename!r}",
                )
                names.add(member.filename)
                normalized_name = member.filename.casefold()
                require(
                    normalized_name not in casefolded_names,
                    f"{catalog_name}: {source_id} contains case-colliding archive members",
                )
                casefolded_names[normalized_name] = member.filename
                require(not (member.flag_bits & 0x1), f"{catalog_name}: {source_id} is encrypted")
                require(
                    member.file_size <= MAX_ARCHIVE_MEMBER_BYTES,
                    f"{catalog_name}: {source_id} member {member.filename!r} is too large",
                )
                total_size += member.file_size
            require(
                total_size <= MAX_ARCHIVE_UNCOMPRESSED_BYTES,
                f"{catalog_name}: {source_id} has an unsafe uncompressed archive size",
            )
            require(
                {name.casefold() for name in REQUIRED_AIX_MEMBERS}.issubset(casefolded_names),
                f"{catalog_name}: {source_id} is missing required AIX payload members",
            )
            bad_member = archive.testzip()
            require(
                bad_member is None,
                f"{catalog_name}: {source_id} has a corrupt archive member {bad_member!r}",
            )

            try:
                manifest_name = casefolded_names["payload/source.json"]
                manifest = json.loads(archive.read(manifest_name).decode("utf-8-sig"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ValidationFailure(
                    f"{catalog_name}: {source_id} has an invalid Payload/source.json: {error}"
                ) from error
            info = manifest.get("info") if isinstance(manifest, dict) else None
            require(isinstance(info, dict), f"{catalog_name}: {source_id} has no manifest info object")
            require(
                info.get("id") == source_id,
                f"{catalog_name}: {source_id} package manifest id does not match the catalog",
            )
            require(
                info.get("version") == entry["version"],
                f"{catalog_name}: {source_id} package manifest version does not match the catalog",
            )
            with archive.open(casefolded_names["payload/main.wasm"]) as wasm_file:
                wasm_header = wasm_file.read(4)
            require(
                wasm_header == b"\x00asm",
                f"{catalog_name}: {source_id} main.wasm has an invalid header",
            )
            with archive.open(casefolded_names["payload/icon.png"]) as icon_file:
                icon_header = icon_file.read(8)
            require(
                icon_header == b"\x89PNG\r\n\x1a\n",
                f"{catalog_name}: {source_id} icon has an invalid PNG header",
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise ValidationFailure(f"{catalog_name}: cannot open {source_id} package: {error}") from error

    digest = hashlib.sha256()
    with path.open("rb") as package_file:
        for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValidationFailure(f"cannot read checksum file {path}: {error}") from error
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\s]+)", line)
        require(match is not None, f"{path}:{line_number}: invalid checksum line")
        digest, relative_path = match.groups()
        require(relative_path not in checksums, f"{path}: duplicate checksum for {relative_path}")
        checksums[relative_path] = digest
    return checksums


def validate_inventory(
    catalog_root: Path,
    catalog_name: str,
    entries: list[dict],
    package_hashes: dict[str, str],
) -> None:
    inventory = load_json(catalog_root / "inventory.json")
    require(isinstance(inventory, dict), f"{catalog_name}: inventory must be an object")
    require(
        inventory.get("sourceCount") == len(entries),
        f"{catalog_name}: inventory sourceCount does not match the index",
    )
    generated_at = inventory.get("generatedAt")
    try:
        parsed_timestamp = datetime.fromisoformat(generated_at) if isinstance(generated_at, str) else None
    except ValueError as error:
        raise ValidationFailure(f"{catalog_name}: invalid generatedAt timestamp {generated_at!r}") from error
    require(
        parsed_timestamp is not None and parsed_timestamp.tzinfo is not None,
        f"{catalog_name}: generatedAt must be a timezone-aware ISO timestamp",
    )

    inventory_entries = inventory.get("sources")
    require(isinstance(inventory_entries, list), f"{catalog_name}: inventory sources must be a list")
    require(
        len(inventory_entries) == len(entries),
        f"{catalog_name}: inventory source list length does not match the index",
    )
    indexed_by_id = {entry["id"]: entry for entry in entries}
    inventory_ids: list[str] = []
    for inventory_entry in inventory_entries:
        require(isinstance(inventory_entry, dict), f"{catalog_name}: invalid inventory source entry")
        source_id = inventory_entry.get("id")
        require(source_id in indexed_by_id, f"{catalog_name}: unknown inventory source {source_id!r}")
        require(source_id not in inventory_ids, f"{catalog_name}: duplicate inventory source {source_id}")
        inventory_ids.append(source_id)
        indexed_entry = indexed_by_id[source_id]
        require(
            inventory_entry.get("version") == indexed_entry["version"],
            f"{catalog_name}: {source_id} inventory version mismatch",
        )
        require(
            inventory_entry.get("file") == indexed_entry["downloadURL"],
            f"{catalog_name}: {source_id} inventory file mismatch",
        )
        digest = inventory_entry.get("sha256")
        require(
            isinstance(digest, str)
            and SHA256_PATTERN.fullmatch(digest) is not None
            and digest == package_hashes[source_id],
            f"{catalog_name}: {source_id} inventory checksum mismatch",
        )
        provenance_url = inventory_entry.get("upstreamPackageURL")
        if provenance_url is not None:
            require(
                isinstance(provenance_url, str),
                f"{catalog_name}: {source_id} upstream package URL must be a string",
            )
            parsed_provenance = urlsplit(provenance_url)
            require(
                parsed_provenance.scheme == "https"
                and bool(parsed_provenance.hostname)
                and not parsed_provenance.username
                and not parsed_provenance.password,
                f"{catalog_name}: {source_id} has an unsafe upstream package URL",
            )
    require(
        inventory_ids == sorted(inventory_ids),
        f"{catalog_name}: inventory sources are not sorted by id",
    )

    checksums = parse_checksums(catalog_root / "CHECKSUMS.sha256")
    expected_checksums = {
        entry["downloadURL"]: package_hashes[entry["id"]]
        for entry in entries
    }
    require(checksums == expected_checksums, f"{catalog_name}: CHECKSUMS.sha256 is incomplete or stale")


def validate_catalog(catalog_root: Path, catalog_name: str, minimum_sources: int) -> set[str]:
    index = load_json(catalog_root / "index.json")
    compact_index = load_json(catalog_root / "index.min.json")
    require(index == compact_index, f"{catalog_name}: index.json and index.min.json differ")
    require(isinstance(index, dict), f"{catalog_name}: index must be an object")
    require(
        isinstance(index.get("name"), str) and bool(index["name"].strip()),
        f"{catalog_name}: catalog name is missing",
    )
    entries = index.get("sources")
    require(isinstance(entries, list), f"{catalog_name}: sources must be a list")
    require(
        len(entries) >= minimum_sources,
        f"{catalog_name}: only {len(entries)} sources; expected at least {minimum_sources}",
    )

    source_ids: list[str] = []
    package_paths: set[str] = set()
    icon_paths: set[str] = set()
    package_hashes: dict[str, str] = {}
    for entry in entries:
        source_id, package_path, icon_path = validate_source_entry(entry, catalog_name)
        require(source_id not in source_ids, f"{catalog_name}: duplicate source id {source_id}")
        require(str(package_path) not in package_paths, f"{catalog_name}: duplicate package path {package_path}")
        require(str(icon_path) not in icon_paths, f"{catalog_name}: duplicate icon path {icon_path}")
        source_ids.append(source_id)
        package_paths.add(str(package_path))
        icon_paths.add(str(icon_path))

        package_file = catalog_root.joinpath(*package_path.parts)
        icon_file = catalog_root.joinpath(*icon_path.parts)
        require(
            icon_file.is_file() and not icon_file.is_symlink(),
            f"{catalog_name}: missing or unsafe icon for {source_id}: {icon_file}",
        )
        require(
            icon_file.stat().st_size <= MAX_PUBLISHED_ICON_BYTES,
            f"{catalog_name}: published icon is too large for {source_id}",
        )
        try:
            with icon_file.open("rb") as published_icon:
                icon_header = published_icon.read(8)
        except OSError as error:
            raise ValidationFailure(f"{catalog_name}: cannot read icon for {source_id}: {error}") from error
        require(icon_header == b"\x89PNG\r\n\x1a\n", f"{catalog_name}: invalid PNG icon for {source_id}")
        package_hashes[source_id] = validate_aix(package_file, entry, catalog_name)

    require(source_ids == sorted(source_ids), f"{catalog_name}: index sources are not sorted by id")
    referenced_packages = {Path(path).name for path in package_paths}
    referenced_icons = {Path(path).name for path in icon_paths}
    actual_packages = {
        path.relative_to(catalog_root / "sources").as_posix()
        for path in (catalog_root / "sources").rglob("*")
        if path.is_file() or path.is_symlink()
    }
    actual_icons = {
        path.relative_to(catalog_root / "icons").as_posix()
        for path in (catalog_root / "icons").rglob("*")
        if path.is_file() or path.is_symlink()
    }
    require(
        actual_packages == referenced_packages,
        f"{catalog_name}: sources/ contains missing or unreferenced packages",
    )
    require(
        actual_icons == referenced_icons,
        f"{catalog_name}: icons/ contains missing or unreferenced icons",
    )
    validate_inventory(catalog_root, catalog_name, entries, package_hashes)
    return set(source_ids)


def validate_policy(root: Path, maintained_ids: set[str], legacy_ids: set[str]) -> None:
    policy = load_json(root / "config" / "source_policy.json")
    require(isinstance(policy, dict), "source policy must be an object")

    quarantined_sources = policy.get("quarantinedSources")
    require(isinstance(quarantined_sources, dict), "source policy quarantinedSources must be an object")
    for source_id, details in quarantined_sources.items():
        require(
            isinstance(source_id, str) and SOURCE_ID_PATTERN.fullmatch(source_id) is not None,
            f"source policy contains an invalid quarantined id {source_id!r}",
        )
        require(isinstance(details, dict), f"source policy details for {source_id} must be an object")
        require(
            isinstance(details.get("reason"), str) and bool(details["reason"].strip()),
            f"source policy reason for {source_id} is missing",
        )
        if "name" in details:
            require(
                isinstance(details["name"], str) and bool(details["name"].strip()),
                f"source policy name for {source_id} is invalid",
            )
        if "issue" in details:
            issue = urlsplit(details["issue"]) if isinstance(details["issue"], str) else None
            require(
                issue is not None and issue.scheme == "https" and bool(issue.hostname),
                f"source policy issue for {source_id} is unsafe",
            )
        catalogs = details.get("catalogs")
        require(
            isinstance(catalogs, list)
            and bool(catalogs)
            and all(catalog in {"maintained", "legacy"} for catalog in catalogs),
            f"source policy catalogs for {source_id} are invalid",
        )
        require(
            not ("maintained" in catalogs and source_id in maintained_ids),
            f"quarantined source {source_id} is still present in the maintained catalog",
        )
        require(
            not ("legacy" in catalogs and source_id in legacy_ids),
            f"quarantined source {source_id} is still present in the legacy catalog",
        )

    required_sources = policy.get("requiredMaintainedSources")
    require(isinstance(required_sources, list), "source policy requiredMaintainedSources must be a list")
    require(
        all(isinstance(source_id, str) for source_id in required_sources),
        "source policy requiredMaintainedSources contains an invalid id",
    )
    missing_required = set(required_sources) - maintained_ids
    require(
        not missing_required,
        "required maintained sources are missing: " + ", ".join(sorted(missing_required)),
    )

    safety = policy.get("safety")
    require(isinstance(safety, dict), "source policy safety must be an object")
    minimum_maintained = safety.get("minimumMaintainedSources")
    minimum_legacy = safety.get("minimumLegacySources")
    require(
        isinstance(minimum_maintained, int) and minimum_maintained >= 1,
        "source policy minimumMaintainedSources must be a positive integer",
    )
    require(
        isinstance(minimum_legacy, int) and minimum_legacy >= 0,
        "source policy minimumLegacySources must be a non-negative integer",
    )
    require(
        len(maintained_ids) >= minimum_maintained,
        f"maintained catalog has {len(maintained_ids)} sources; policy requires {minimum_maintained}",
    )
    require(
        len(legacy_ids) >= minimum_legacy,
        f"legacy catalog has {len(legacy_ids)} sources; policy requires {minimum_legacy}",
    )


def validate_status(root: Path, maintained_ids: set[str], legacy_ids: set[str]) -> None:
    status = load_json(root / "status.json")
    require(isinstance(status, dict), "status report must be an object")
    try:
        status_timestamp = datetime.fromisoformat(status.get("generatedAt", ""))
    except (TypeError, ValueError) as error:
        raise ValidationFailure("status generatedAt is not a valid ISO timestamp") from error
    require(status_timestamp.tzinfo is not None, "status generatedAt must include a timezone")
    summary = status.get("summary")
    require(isinstance(summary, dict), "status report summary must be an object")
    require(summary.get("maintained") == len(maintained_ids), "status maintained count is stale")
    require(summary.get("legacyOnly") == len(legacy_ids), "status legacy count is stale")

    policy = load_json(root / "config" / "source_policy.json")
    health = load_json(root / "config" / "source_health.json")
    manual = status.get("manualQuarantine")
    automatic = status.get("automaticQuarantine")
    degraded = status.get("degraded")
    require(all(isinstance(value, list) for value in (manual, automatic, degraded)), "invalid status lists")
    require(
        all(isinstance(entry, dict) for entries in (manual, automatic, degraded) for entry in entries),
        "status lists must contain only objects",
    )
    for entries in (manual, automatic, degraded):
        for entry in entries:
            source_id = entry.get("id")
            require(
                isinstance(source_id, str) and SOURCE_ID_PATTERN.fullmatch(source_id) is not None,
                f"status contains invalid source id {source_id!r}",
            )
    require(summary.get("manualQuarantined") == len(manual), "status manual count is stale")
    require(summary.get("automaticQuarantined") == len(automatic), "status automatic count is stale")
    require(summary.get("degraded") == len(degraded), "status degraded count is stale")
    manual_ids = {entry["id"] for entry in manual}
    require(
        manual_ids == set(policy.get("quarantinedSources", {})),
        "status manual quarantine does not match source policy",
    )
    automatic_ids = {entry["id"] for entry in automatic}
    degraded_ids = {entry["id"] for entry in degraded}
    require(len(manual_ids) == len(manual), "status contains duplicate manual entries")
    require(len(automatic_ids) == len(automatic), "status contains duplicate automatic entries")
    require(len(degraded_ids) == len(degraded), "status contains duplicate degraded entries")
    health_ids = set(health.get("sources", {}))
    require(automatic_ids.isdisjoint(degraded_ids), "status source is both quarantined and degraded")
    require(
        manual_ids.isdisjoint(automatic_ids | degraded_ids),
        "manual quarantine is duplicated in automatic health status",
    )
    require(automatic_ids | degraded_ids == health_ids, "status health entries do not match health state")
    require(
        manual_ids.isdisjoint(maintained_ids | legacy_ids),
        "manually quarantined status source is still installable",
    )
    require(
        automatic_ids.isdisjoint(maintained_ids | legacy_ids),
        "automatically quarantined status source is still installable",
    )
    markdown = root / "status.md"
    require(markdown.is_file() and markdown.stat().st_size > 100, "status.md is missing or empty")


def validate_repository(root: Path) -> tuple[int, int]:
    maintained_ids = validate_catalog(root, "maintained catalog", minimum_sources=20)
    legacy_ids = validate_catalog(root / "legacy", "legacy catalog", minimum_sources=0)
    overlap = maintained_ids & legacy_ids
    require(
        not overlap,
        "legacy catalog must contain only legacy-only sources; overlap: " + ", ".join(sorted(overlap)),
    )
    validate_policy(root, maintained_ids, legacy_ids)
    validate_status(root, maintained_ids, legacy_ids)
    return len(maintained_ids), len(legacy_ids)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root containing index.json (default: script repository)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        maintained_count, legacy_count = validate_repository(args.root.resolve())
    except ValidationFailure as error:
        print(f"catalog validation failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Validated {maintained_count} maintained and {legacy_count} legacy-only sources "
        "with no catalog overlap."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
