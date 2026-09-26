#!/usr/bin/env python3
"""Refresh Nixzle's public Aidoku source lists from redistributable upstreams.

The updater deliberately fails closed around package metadata, but a transient
failure for one package can fall back to that source's last validated package.
Catalogs are written only after both maintained and legacy selections pass
safety checks.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import random
import re
import socket
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import ipaddress
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

try:
    from scripts import source_health
except ModuleNotFoundError:
    import source_health


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "source_policy.json"
HEALTH_STATE_PATH = ROOT / "config" / "source_health.json"
STATUS_JSON_PATH = ROOT / "status.json"
STATUS_MARKDOWN_PATH = ROOT / "status.md"
ROLLBACK_PATH = ROOT / "rollback" / "last-known-good.json"
USER_AGENT = "Nixzle-Aidoku-Sources-Updater/2.0"
TIMEOUT_SECONDS = 45
HEALTH_TIMEOUT_SECONDS = 12
FETCH_ATTEMPTS = 3
DOWNLOAD_WORKERS = 12
HEALTH_WORKERS = 12
MAX_INDEX_BYTES = 10 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_ICON_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_ENTRIES = 128
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 32 * 1024 * 1024
ENGLISH_MARKERS = {"en", "all", "multi"}
PROTECTED_HTTP_STATUSES = {401, 403, 429, 451}
SOURCE_ID_RE = re.compile(r"^(?:en|multi)\.[a-z0-9][a-z0-9._-]{0,127}$")
APP_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?$")
SOURCE_PREFERENCES: dict[str, str] = {}
ACTIVE_REPOSITORY = "Aidoku-Community/sources"

# Only repositories whose packages may be publicly redistributed are included.
# Higher priority wins when two repositories publish the same source or website.
UPSTREAMS = (
    {
        "name": "Aidoku-Community/sources",
        "index": "https://aidoku-community.github.io/sources/index.min.json",
        "asset_base": "https://aidoku-community.github.io/sources/",
        "priority": 300,
        "license": "MIT OR Apache-2.0",
    },
    {
        "name": "tachibana-shin/aidoku-sources-next",
        "index": "https://raw.githubusercontent.com/tachibana-shin/aidoku-sources-next/gh-pages/index.min.json",
        "asset_base": "https://raw.githubusercontent.com/tachibana-shin/aidoku-sources-next/gh-pages/",
        "priority": 200,
        "license": "MIT OR Apache-2.0",
    },
    {
        "name": "tachibana-shin/aidoku-community-sources",
        "index": "https://raw.githubusercontent.com/tachibana-shin/aidoku-community-sources/gh-pages/index.min.json",
        "asset_base": "https://raw.githubusercontent.com/tachibana-shin/aidoku-community-sources/gh-pages/",
        "priority": 100,
        "license": "MIT OR Apache-2.0",
    },
)


def _safe_https_url(url: str, label: str, allowed_hosts: set[str] | None = None):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError(f"{label} is not a sane URL")
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not contain credentials")
    host = parsed.hostname.casefold()
    if allowed_hosts and host not in {value.casefold() for value in allowed_hosts}:
        raise ValueError(f"{label} redirected to unapproved host {host}")
    return parsed


def _is_public_host(host: str) -> bool:
    """Reject literal and resolved non-global addresses used by health probes."""
    normalized = host.casefold().rstrip(".")
    if normalized == "localhost" or normalized.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        addresses = {ipaddress.ip_address(normalized)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0].split("%", 1)[0])
                for item in socket.getaddrinfo(normalized, 443, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            # DNS/network failures are ordinary health failures, not safe targets.
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect before urllib sends the redirected request."""

    def __init__(self, allowed_hosts: set[str], *, require_public: bool = False):
        super().__init__()
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}
        self.require_public = require_public

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = _safe_https_url(newurl, "redirect URL", self.allowed_hosts)
        if self.require_public and not _is_public_host(parsed.hostname):
            raise urllib.error.URLError(f"redirect target is not public: {parsed.hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(request, *, timeout: int, allowed_hosts: set[str], require_public: bool = False):
    handler = _SafeRedirectHandler(allowed_hosts, require_public=require_public)
    return urllib.request.build_opener(handler).open(request, timeout=timeout)


def _read_limited(response, maximum: int, label: str) -> bytes:
    content_length = response.headers.get("Content-Length") if response.headers else None
    if content_length:
        try:
            if int(content_length) > maximum:
                raise ValueError(f"{label} exceeds the {maximum}-byte limit")
        except ValueError as error:
            if "exceeds" in str(error):
                raise
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise ValueError(f"{label} exceeds the {maximum}-byte limit")
    return b"".join(chunks)


def fetch_bytes(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    maximum: int = MAX_PACKAGE_BYTES,
    attempts: int = FETCH_ATTEMPTS,
    timeout: int = TIMEOUT_SECONDS,
) -> bytes:
    """Fetch HTTPS content with bounded retries, redirect checks, and a size cap."""
    initial = _safe_https_url(url, "download URL", allowed_hosts)
    allowed = allowed_hosts or {initial.hostname.casefold()}
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with _open_url(request, timeout=timeout, allowed_hosts=allowed) as response:
                status = int(getattr(response, "status", response.getcode()))
                if status != 200:
                    error = RuntimeError(f"HTTP {status} for {url}")
                    if status not in {408, 425, 429} and status < 500:
                        raise error
                    last_error = error
                else:
                    final_url = response.geturl() if hasattr(response, "geturl") else url
                    _safe_https_url(final_url, "final download URL", allowed)
                    return _read_limited(response, maximum, url)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 425, 429} and error.code < 500:
                raise RuntimeError(f"HTTP {error.code} for {url}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last_error = error
        if attempt + 1 < max(1, attempts):
            time.sleep((0.5 * (2**attempt)) + random.uniform(0, 0.25))
    raise RuntimeError(f"Unable to fetch {url} after {max(1, attempts)} attempts: {last_error}")


def fetch_json(url: str, *, allowed_hosts: set[str] | None = None):
    payload = fetch_bytes(url, allowed_hosts=allowed_hosts, maximum=MAX_INDEX_BYTES)
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON from {url}: {error}") from error


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def entry_languages(entry: dict) -> list[str]:
    return [str(value) for value in as_list(entry.get("languages", entry.get("lang")))]


def is_english_entry(entry: dict) -> bool:
    source_id = str(entry.get("id", "")).casefold()
    return (
        source_id.startswith(("en.", "multi."))
        and any(language.casefold() in ENGLISH_MARKERS for language in entry_languages(entry))
    )


def validate_source_id(source_id: str, label: str = "source ID") -> str:
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError(f"Unsafe {label}: {source_id!r}")
    return source_id


def normalized_url_key(urls: list[str]) -> str | None:
    for value in urls:
        try:
            parsed = urlparse(value)
            if not parsed.hostname:
                continue
            host = parsed.hostname.casefold()
            if host.startswith("www."):
                host = host[4:]
            path = parsed.path.rstrip("/").casefold()
            return f"{host}{path}"
        except ValueError:
            continue
    return None


def package_url(upstream: dict, entry: dict) -> str:
    reference = entry.get("downloadURL")
    if not reference:
        filename = entry.get("file")
        reference = f"sources/{filename}" if filename else None
    if not isinstance(reference, str) or not reference:
        raise ValueError(f"Source {entry.get('id', '<unknown>')} has no package reference")
    parsed_reference = urlparse(reference)
    decoded_path = unquote(parsed_reference.path)
    if (
        parsed_reference.scheme
        or parsed_reference.netloc
        or parsed_reference.fragment
        or parsed_reference.query
        or decoded_path.startswith(("/", "\\"))
        or "\\" in decoded_path
        or ".." in PurePosixPath(decoded_path).parts
    ):
        raise ValueError(f"Unsafe package reference for {entry.get('id', '<unknown>')}: {reference}")

    base = str(upstream["asset_base"])
    base_parsed = _safe_https_url(base, f"asset base for {upstream['name']}")
    candidate = urljoin(base, reference)
    candidate_parsed = _safe_https_url(
        candidate,
        f"package URL for {entry.get('id', '<unknown>')}",
        {base_parsed.hostname.casefold()},
    )
    base_path = base_parsed.path if base_parsed.path.endswith("/") else f"{base_parsed.path}/"
    if not candidate_parsed.path.startswith(base_path):
        raise ValueError(f"Package reference escapes the asset base: {reference}")
    return candidate


def read_package(
    package: bytes,
    label: str,
    *,
    expected_id: str | None = None,
    expected_version: int | None = None,
) -> tuple[dict, bytes]:
    if not package or len(package) > MAX_PACKAGE_BYTES:
        raise ValueError(f"{label} has an invalid package size")
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(f"{label} contains too many archive entries")
            total_size = 0
            names: dict[str, str] = {}
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (
                    not entry.filename
                    or entry.filename.startswith(("/", "\\"))
                    or "\\" in entry.filename
                    or ".." in path.parts
                    or entry.flag_bits & 0x1
                ):
                    raise ValueError(f"{label} contains an unsafe archive entry")
                folded = entry.filename.casefold()
                if folded in names:
                    raise ValueError(f"{label} contains duplicate archive paths")
                names[folded] = entry.filename
                if entry.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                    raise ValueError(f"{label} contains an oversized archive entry")
                total_size += entry.file_size
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError(f"{label} expands beyond the archive size limit")

            required = ("payload/source.json", "payload/main.wasm", "payload/icon.png")
            missing = [name for name in required if name not in names]
            if missing:
                raise ValueError(f"{label} is missing {', '.join(missing)}")
            manifest_entry = archive.getinfo(names["payload/source.json"])
            icon_entry = archive.getinfo(names["payload/icon.png"])
            if manifest_entry.file_size > MAX_MANIFEST_BYTES:
                raise ValueError(f"{label} contains an oversized manifest")
            if icon_entry.file_size > MAX_ICON_BYTES:
                raise ValueError(f"{label} contains an oversized icon")

            manifest_bytes = archive.read(names["payload/source.json"])
            wasm = archive.read(names["payload/main.wasm"])
            icon = archive.read(names["payload/icon.png"])
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as error:
        raise ValueError(f"{label} is not a safe readable AIX archive: {error}") from error

    if not wasm.startswith(b"\x00asm\x01\x00\x00\x00"):
        raise ValueError(f"{label} contains an invalid WebAssembly payload")
    if not icon.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"{label} icon is not a PNG")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} contains an invalid manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError(f"{label} manifest must be an object")
    info = manifest.get("info", manifest)
    if not isinstance(info, dict):
        raise ValueError(f"{label} manifest info must be an object")

    manifest_id = validate_source_id(str(info.get("id", "")), "manifest source ID")
    try:
        manifest_version = int(info["version"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{label} manifest has no valid version") from error
    if not 1 <= manifest_version <= 1_000_000:
        raise ValueError(f"{label} manifest version is outside the accepted range")
    if expected_id is not None and manifest_id != expected_id:
        raise ValueError(f"{label} manifest ID {manifest_id!r} does not match {expected_id!r}")
    if expected_version is not None and manifest_version != expected_version:
        raise ValueError(
            f"{label} manifest version {manifest_version} does not match index version {expected_version}"
        )
    return info, icon


def load_current(catalog_root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    index_path = catalog_root / "index.min.json"
    inventory_path = catalog_root / "inventory.json"
    if not index_path.exists() or not inventory_path.exists():
        return {}, {}
    try:
        index = json.loads(index_path.read_text(encoding="utf-8-sig"))
        inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to read current catalog at {catalog_root}: {error}") from error
    return (
        {entry["id"]: entry for entry in index.get("sources", [])},
        {entry["id"]: entry for entry in inventory.get("sources", [])},
    )


def _safe_local_reference(catalog_root: Path, reference: str) -> Path:
    parsed = urlparse(reference)
    decoded = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or decoded.startswith(("/", "\\"))
        or "\\" in decoded
        or ".." in PurePosixPath(decoded).parts
    ):
        raise ValueError(f"Unsafe local catalog reference: {reference}")
    root = catalog_root.resolve()
    path = (root / Path(*PurePosixPath(decoded).parts)).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Local catalog reference escapes its root: {reference}")
    return path


def build_package_cache(catalog_roots: tuple[Path, ...]) -> dict[tuple[str, str, int], bytes]:
    """Load checksum-verified packages, retaining the catalog root in resolution."""
    cache: dict[tuple[str, str, int], bytes] = {}
    for catalog_root in catalog_roots:
        current_index, current_inventory = load_current(catalog_root)
        for source_id, inventory in current_inventory.items():
            try:
                validate_source_id(source_id)
                index_entry = current_index[source_id]
                version = int(index_entry["version"])
                repository = str(inventory["repository"])
                reference = str(index_entry["downloadURL"])
                path = _safe_local_reference(catalog_root, reference)
                package = path.read_bytes()
                expected_digest = str(inventory["sha256"]).casefold()
                if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
                    raise ValueError("inventory contains an invalid SHA-256")
                if hashlib.sha256(package).hexdigest() != expected_digest:
                    raise ValueError("cached package checksum does not match inventory")
                cache.setdefault((repository, source_id, version), package)
            except (KeyError, OSError, TypeError, ValueError) as error:
                print(f"WARNING: ignoring invalid cache entry {catalog_root}:{source_id}: {error}")
    return cache


def _cached_package(
    cache: dict[tuple[str, str, int], bytes], upstream: dict, source_id: str, version: int
) -> tuple[int, bytes] | None:
    exact = cache.get((upstream["name"], source_id, version))
    if exact is not None:
        return version, exact
    matches = [
        (cached_version, package)
        for (repository, cached_id, cached_version), package in cache.items()
        if repository == upstream["name"] and cached_id == source_id
    ]
    return max(matches, key=lambda value: value[0]) if matches else None


def _source_urls(info: dict, entry: dict, label: str) -> list[str]:
    urls = [str(value) for value in as_list(info.get("urls"))]
    if info.get("url"):
        urls.insert(0, str(info["url"]))
    if not urls and entry.get("baseURL"):
        urls.append(str(entry["baseURL"]))
    cleaned: list[str] = []
    for index, value in enumerate(urls):
        _safe_https_url(value, f"{label} website URL {index + 1}")
        if value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        raise ValueError(f"{label} has no valid website URL")
    return cleaned


def candidate_from_package(
    upstream: dict,
    entry: dict,
    package: bytes,
    *,
    expected_version: int,
    min_app_version_overrides: dict[str, str],
    upstream_package_url: str | None = None,
) -> dict:
    source_id = validate_source_id(str(entry.get("id", "")))
    label = f"{upstream['name']}:{source_id}"
    info, icon = read_package(
        package,
        label,
        expected_id=source_id,
        expected_version=expected_version,
    )
    name = str(info.get("name") or entry.get("name") or source_id).strip()
    if not name or len(name) > 200:
        raise ValueError(f"{label} has an invalid source name")
    languages = [str(value) for value in as_list(info.get("languages", info.get("lang")))]
    if not languages:
        languages = entry_languages(entry)
    if not any(language.casefold() in ENGLISH_MARKERS for language in languages):
        raise ValueError(f"{source_id} package no longer advertises English or multilingual support")
    if any(not value or len(value) > 32 for value in languages):
        raise ValueError(f"{source_id} contains an invalid language marker")

    urls = _source_urls(info, entry, label)
    content_rating = info.get("contentRating", info.get("nsfw"))
    if content_rating is None:
        content_rating = entry.get("contentRating", entry.get("nsfw", 0))
    try:
        content_rating = int(content_rating)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} has an invalid content rating") from error
    if content_rating not in {0, 1, 2}:
        raise ValueError(f"{label} has an out-of-range content rating")

    minimum_app_version = min_app_version_overrides.get(
        source_id,
        info.get("minAppVersion", entry.get("minAppVersion")),
    )
    if minimum_app_version is not None:
        minimum_app_version = str(minimum_app_version)
        if len(minimum_app_version) > 32 or not APP_VERSION_RE.fullmatch(minimum_app_version):
            raise ValueError(f"{label} has an invalid minimum app version")

    return {
        "id": source_id,
        "name": name,
        "version": expected_version,
        "languages": languages,
        "contentRating": content_rating,
        "baseURL": urls[0],
        "minAppVersion": minimum_app_version,
        "urls": urls,
        "urlKey": normalized_url_key(urls),
        "package": package,
        "icon": icon,
        "repository": upstream["name"],
        "priority": int(upstream["priority"]),
        "license": upstream["license"],
        "upstreamPackageURL": upstream_package_url,
    }


def candidate_from_entry(
    upstream: dict,
    entry: dict,
    cache: dict[tuple[str, str, int], bytes],
    min_app_version_overrides: dict[str, str],
    refresh_cached: bool = False,
) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"{upstream['name']} contains a non-object source entry")
    source_id = validate_source_id(str(entry.get("id", "")))
    try:
        version = int(entry["version"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{source_id} has no valid index version") from error
    if not 1 <= version <= 1_000_000:
        raise ValueError(f"{source_id} index version is outside the accepted range")
    upstream_package_url = package_url(upstream, entry)

    # Treat a published (repository, ID, version) as immutable. This prevents a
    # same-version upstream rebuild from silently changing bytes behind an
    # already-public download URL. New bytes require a new source version.
    exact_package = cache.get((upstream["name"], source_id, version))
    if exact_package is not None and not refresh_cached:
        try:
            return candidate_from_package(
                upstream,
                entry,
                exact_package,
                expected_version=version,
                min_app_version_overrides=min_app_version_overrides,
                upstream_package_url=upstream_package_url,
            )
        except Exception as error:
            print(
                f"WARNING: cached immutable package {upstream['name']}:{source_id} "
                f"v{version} is invalid; attempting a clean download: {error}"
            )

    live_error: Exception | None = None
    try:
        url = upstream_package_url
        host = _safe_https_url(str(upstream["asset_base"]), "asset base").hostname.casefold()
        package = fetch_bytes(url, allowed_hosts={host}, maximum=MAX_PACKAGE_BYTES)
        return candidate_from_package(
            upstream,
            entry,
            package,
            expected_version=version,
            min_app_version_overrides=min_app_version_overrides,
            upstream_package_url=url,
        )
    except Exception as error:  # source-level isolation is applied by the caller
        live_error = error

    cached = _cached_package(cache, upstream, source_id, version)
    if cached is None:
        raise RuntimeError(f"{upstream['name']}:{source_id} failed with no cache: {live_error}") from live_error
    cached_version, package = cached
    cached_entry = dict(entry)
    cached_entry["version"] = cached_version
    try:
        candidate = candidate_from_package(
            upstream,
            cached_entry,
            package,
            expected_version=cached_version,
            min_app_version_overrides=min_app_version_overrides,
        )
    except Exception as cache_error:
        raise RuntimeError(
            f"{upstream['name']}:{source_id} live package failed ({live_error}); "
            f"last-known-good cache is invalid ({cache_error})"
        ) from cache_error
    print(
        f"WARNING: {upstream['name']}:{source_id} live package failed; "
        f"using validated cached v{cached_version}: {live_error}"
    )
    return candidate


def select_candidates(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    by_id: dict[str, dict] = {}
    for candidate in candidates:
        current = by_id.get(candidate["id"])
        preferred_repository = SOURCE_PREFERENCES.get(candidate["id"])
        rank = (
            candidate["repository"] == preferred_repository,
            candidate["priority"],
            candidate["version"],
        )
        current_rank = (
            current is not None and current["repository"] == preferred_repository,
            current["priority"] if current else -1,
            current["version"] if current else -1,
        )
        if current is None or rank > current_rank:
            by_id[candidate["id"]] = candidate

    selected_by_site: dict[str, dict] = {}
    duplicates: list[dict] = []
    for candidate in sorted(by_id.values(), key=lambda item: item["id"]):
        key = candidate["urlKey"] or f"id:{candidate['id']}"
        current = selected_by_site.get(key)
        if current is None:
            selected_by_site[key] = candidate
            continue
        if (candidate["priority"], candidate["version"]) > (
            current["priority"],
            current["version"],
        ):
            kept, excluded = candidate, current
            selected_by_site[key] = candidate
        else:
            kept, excluded = current, candidate
        duplicates.append(
            {
                "excludedId": excluded["id"],
                "keptId": kept["id"],
                "normalizedSite": key,
            }
        )
    return sorted(selected_by_site.values(), key=lambda item: item["id"]), duplicates


def override_provenance(detail: dict) -> dict:
    provenance = str(detail["provenanceURL"])
    parsed = _safe_https_url(provenance, "override provenance")
    download = detail.get("downloadURL", provenance)
    metadata = {"provenanceURL": provenance}
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname == "github.com" and len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _, commit, *path = parts
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Override provenance must be pinned to a full commit SHA")
        package_path = "/".join(path)
        expected = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{package_path}"
        if detail.get("downloadURL") and download != expected:
            raise ValueError("Override download URL does not match its provenance commit/path")
        download = expected
        metadata.update(packageRepository=f"{owner}/{repo}", sourceCommit=commit, sourcePath=package_path)
        for key in ("sourceCommit", "sourcePath"):
            if detail.get(key) is not None and detail[key] != metadata[key]:
                raise ValueError(f"Override {key} does not match provenance")
    candidate = _safe_https_url(str(download), "override download")
    if candidate.hostname == "github.com" and "/blob/" in candidate.path:
        raise ValueError("An HTML blob page is not a package download URL")
    metadata["upstreamPackageURL"] = str(download)
    return metadata


def apply_local_package_overrides(
    candidates: list[dict],
    policy: dict,
    *,
    root: Path = ROOT,
) -> list[dict]:
    """Replace active-upstream packages with reviewed, repository-pinned fixes.

    Overrides remain explicit policy rather than an invisible preference. The
    package is used until a newer upstream version supersedes it, and it
    is subjected to the same manifest/archive validation as downloaded AIX
    files. This lets a compatibility fix survive the nightly mirror refresh.
    """
    overrides = policy.get("localPackageOverrides", {})
    if not overrides:
        return candidates
    active_upstream = next(
        upstream for upstream in UPSTREAMS if upstream["name"] == ACTIVE_REPOSITORY
    )
    result = list(candidates)
    for source_id, detail in sorted(overrides.items()):
        path = _safe_local_reference(root, str(detail["path"]))
        override_root = (root / "overrides").resolve()
        if override_root not in path.parents or path.suffix.casefold() != ".aix":
            raise ValueError(f"Local override for {source_id} must be an .aix inside overrides/")
        package = path.read_bytes()
        expected_digest = detail.get("sha256")
        if expected_digest and hashlib.sha256(package).hexdigest() != expected_digest:
            raise ValueError(f"Pinned checksum mismatch for {source_id}")
        if len(package) > MAX_PACKAGE_BYTES:
            raise ValueError(f"Local override for {source_id} exceeds the package size limit")
        info, _ = read_package(package, f"local override {source_id}", expected_id=source_id)
        try:
            version = int(info["version"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Local override for {source_id} has no valid version") from error
        active_matches = [
            candidate
            for candidate in result
            if candidate["id"] == source_id and candidate["repository"] == ACTIVE_REPOSITORY
        ]
        if not active_matches:
            raise ValueError(f"Local override source {source_id} is absent from the active upstream")
        upstream_version = max(candidate["version"] for candidate in active_matches)
        if upstream_version > version:
            print(f"Retired local override {source_id} v{version}; upstream is v{upstream_version}")
            continue
        if upstream_version == version:
            upstream_package = max(active_matches, key=lambda item: item["version"])["package"]
            if upstream_package == package:
                print(f"Local override {source_id} matches upstream v{version}")
                for candidate in active_matches:
                    if candidate["package"] == package:
                        candidate.update(override_provenance(detail))
                continue
            print(
                f"::warning::Override conflict for {source_id} v{version}: retaining pinned bytes; "
                "review upstream before replacing this version. Other sources will continue updating."
            )
        entry = {
            "id": source_id,
            "name": info.get("name"),
            "version": version,
            "languages": info.get("languages", info.get("lang")),
            "contentRating": info.get("contentRating", info.get("nsfw")),
            "baseURL": info.get("url"),
            "minAppVersion": info.get("minAppVersion"),
        }
        override = candidate_from_package(
            active_upstream,
            entry,
            package,
            expected_version=version,
            min_app_version_overrides={
                str(key): str(value)
                for key, value in policy.get("minAppVersionOverrides", {}).items()
            },
            upstream_package_url=override_provenance(detail)["upstreamPackageURL"],
        )
        result = [
            candidate
            for candidate in result
            if not (
                candidate["id"] == source_id
                and candidate["repository"] == ACTIVE_REPOSITORY
            )
        ]
        override.update(override_provenance(detail))
        result.append(override)
        print(
            f"Applied reviewed local override {source_id} v{version} "
            f"over active upstream v{upstream_version}"
        )
    return result


def load_policy(path: Path = POLICY_PATH) -> dict:
    try:
        policy = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to load source policy {path}: {error}") from error
    if not isinstance(policy, dict):
        raise ValueError("Source policy must be an object")
    quarantined = policy.get("quarantinedSources", {})
    if not isinstance(quarantined, dict):
        raise ValueError("quarantinedSources must be an object")
    for source_id, detail in quarantined.items():
        validate_source_id(source_id, "quarantined source ID")
        if not isinstance(detail, dict):
            raise ValueError(f"Quarantine policy for {source_id} must be an object")
        name = detail.get("name")
        reason = detail.get("reason")
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
            raise ValueError(f"Quarantine policy for {source_id} has an invalid name")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError(f"Quarantine policy for {source_id} has an invalid reason")
        issue = detail.get("issue")
        if issue is not None:
            _safe_https_url(str(issue), f"quarantine issue for {source_id}")
        scopes = set(as_list(detail.get("catalogs", ["maintained", "legacy"])))
        if not scopes or not scopes <= {"maintained", "legacy"}:
            raise ValueError(f"Quarantine policy for {source_id} has invalid catalogs")
    overrides = policy.get("minAppVersionOverrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("minAppVersionOverrides must be an object")
    for source_id, version in overrides.items():
        validate_source_id(source_id, "minimum-version override source ID")
        if not APP_VERSION_RE.fullmatch(str(version)):
            raise ValueError(f"Invalid minimum-version override for {source_id}")
    package_overrides = policy.get("localPackageOverrides", {})
    if not isinstance(package_overrides, dict):
        raise ValueError("localPackageOverrides must be an object")
    for source_id, detail in package_overrides.items():
        validate_source_id(source_id, "local package override source ID")
        if not isinstance(detail, dict):
            raise ValueError(f"Local package override for {source_id} must be an object")
        path = detail.get("path")
        if not isinstance(path, str) or not path.startswith("overrides/") or len(path) > 300:
            raise ValueError(f"Local package override for {source_id} has an invalid path")
        provenance_url = detail.get("provenanceURL")
        _safe_https_url(str(provenance_url), f"local package override provenance for {source_id}")
    return policy


def excluded_ids(policy: dict, catalog: str) -> set[str]:
    return {
        source_id
        for source_id, detail in policy.get("quarantinedSources", {}).items()
        if catalog in as_list(detail.get("catalogs", ["maintained", "legacy"]))
    }


def _health_state(path: Path = HEALTH_STATE_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "sources": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to read health state {path}: {error}") from error
    if state.get("version") not in (1, 2) or not isinstance(state.get("sources"), dict):
        raise ValueError(f"Unsupported health state in {path}")
    return state


def _health_observation(kind: str, *, reachable: bool, conclusive: bool,
                        http_status: int | None = None, detail: str | None = None) -> dict:
    value = {"kind": kind, "reachable": bool(reachable), "conclusive": bool(conclusive)}
    if http_status is not None:
        value["httpStatus"] = int(http_status)
    if detail:
        value["detail"] = str(detail)[:300]
    return value


def probe_source_health(url: str, *, attempts: int = 2) -> dict:
    """Classify a probe; protection is reachable but not equivalent to functional health."""
    parsed = _safe_https_url(url, "source health URL")
    host = parsed.hostname.casefold()
    if not _is_public_host(host):
        return _health_observation("unsafe_or_unresolvable_host", reachable=False, conclusive=True)
    protected = {401: "auth_required", 403: "protected", 429: "rate_limited", 451: "restricted"}
    last = _health_observation("inconclusive", reachable=False, conclusive=False)
    for attempt in range(max(1, attempts)):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"})
            with _open_url(request, timeout=HEALTH_TIMEOUT_SECONDS, allowed_hosts={host},
                           require_public=True) as response:
                status = int(getattr(response, "status", response.getcode()))
                final_url = response.geturl() if hasattr(response, "geturl") else url
                _safe_https_url(final_url, "final source health URL")
                response.read(1)
                if 200 <= status < 400:
                    return _health_observation("healthy", reachable=True, conclusive=True,
                                               http_status=status)
                if status in protected:
                    return _health_observation(protected[status], reachable=True, conclusive=True,
                                               http_status=status)
                last = _health_observation("http_error", reachable=False, conclusive=True,
                                           http_status=status)
        except urllib.error.HTTPError as error:
            if error.code in protected:
                return _health_observation(protected[error.code], reachable=True, conclusive=True,
                                           http_status=error.code)
            if 400 <= error.code < 600 and error.code not in {408, 425}:
                last = _health_observation("client_error" if error.code < 500 else "server_error",
                                           reachable=False, conclusive=True, http_status=error.code,
                                           detail=str(error.reason or ""))
            else:
                last = _health_observation("transient_http_error", reachable=False, conclusive=False,
                                           http_status=error.code, detail=str(error.reason or ""))
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", None)
            if isinstance(reason, socket.gaierror):
                last = _health_observation("dns_failure", reachable=False, conclusive=True,
                                           detail=str(reason))
            else:
                last = _health_observation("network_error", reachable=False, conclusive=False,
                                           detail=str(reason or error))
        except (TimeoutError, ConnectionError, OSError) as error:
            kind = "dns_failure" if isinstance(error, socket.gaierror) else "network_error"
            last = _health_observation(kind, reachable=False,
                                       conclusive=isinstance(error, socket.gaierror), detail=str(error))
        if attempt + 1 < max(1, attempts):
            time.sleep(0.25 * (2**attempt))
    return last


def probe_source_url(url: str, *, attempts: int = 2) -> bool:
    """Return whether a website is reachable; protected HTTP responses count."""
    parsed = _safe_https_url(url, "source health URL")
    host = parsed.hostname.casefold()
    if not _is_public_host(host):
        return False
    for attempt in range(max(1, attempts)):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
            )
            with _open_url(
                request,
                timeout=HEALTH_TIMEOUT_SECONDS,
                allowed_hosts={host},
                require_public=True,
            ) as response:
                status = int(getattr(response, "status", response.getcode()))
                final_url = response.geturl() if hasattr(response, "geturl") else url
                _safe_https_url(final_url, "final source health URL")
                response.read(1)
                return 200 <= status < 400 or status in PROTECTED_HTTP_STATUSES
        except urllib.error.HTTPError as error:
            if error.code in PROTECTED_HTTP_STATUSES:
                return True
            if 400 <= error.code < 500 and error.code not in {408, 425}:
                return False
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        if attempt + 1 < max(1, attempts):
            time.sleep(0.25 * (2**attempt))
    return False


def observe_source_health(candidates: list[dict], health_policy: dict) -> dict[str, dict]:
    attempts = int(health_policy.get("probeAttempts", 2))
    unique = {candidate["id"]: candidate for candidate in candidates if candidate.get("baseURL")}
    observations = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=HEALTH_WORKERS) as executor:
        futures = {executor.submit(source_health.probe, candidate["baseURL"],
                    opener=_open_url, attempts=attempts, timeout=HEALTH_TIMEOUT_SECONDS): source_id
                   for source_id, candidate in unique.items()}
        for future in concurrent.futures.as_completed(futures):
            source_id = futures[future]
            try:
                observations[source_id] = future.result()
            except Exception:
                observations[source_id] = source_health.observation("probe_error", conclusive=False)
    return observations


def update_health_state(state: dict, observations: dict, *, observation_date: str,
                        failure_threshold: int = 3, recovery_threshold: int = 2,
                        observation_at: str | None = None) -> tuple[dict, set[str]]:
    for source_id in observations:
        validate_source_id(source_id)
    return source_health.transition(state, observations, observation_date=observation_date,
                                   failure_threshold=failure_threshold, recovery_threshold=recovery_threshold, checked_at=observation_at)


def refresh_health_state(candidates: list[dict], policy: dict,
                         state_path: Path = HEALTH_STATE_PATH) -> tuple[set[str], dict]:
    health_policy = policy.get("automaticHealth", {})
    old_state = _health_state(state_path)
    existing = {key for key, value in old_state["sources"].items() if value.get("status") == "quarantined"}
    if not health_policy.get("enabled", True):
        return existing, old_state
    now = source_health.utc_now()
    today = now[:10]
    already_sampled = old_state.get("lastHealthSweepDate", old_state.get("lastSweepDate")) == today
    if old_state.get("version") == 1:
        already_sampled = already_sampled or any(value.get("lastObservationDate") == today
                              for value in old_state["sources"].values())
    if already_sampled:
        return existing, old_state
    observations = observe_source_health(candidates, health_policy)
    for source_id in observations:
        validate_source_id(source_id)
    controls = [source_health.probe(url, opener=_open_url, attempts=1, timeout=8)
                for url in source_health.CONTROL_URLS]
    minimum = float(health_policy.get("minimumConclusiveRatio", 0.5))
    if not 0 <= minimum <= 1:
        raise ValueError("minimumConclusiveRatio must be between zero and one")
    quality = source_health.sweep_quality(observations, controls, minimum)
    new_state, quarantined = source_health.transition(
        old_state, observations, observation_date=today, checked_at=now,
        failure_threshold=int(health_policy.get("failureThreshold", 3)),
        recovery_threshold=int(health_policy.get("recoveryThreshold", 2)),
        required_ids=policy.get("requiredMaintainedSources", []), accepted=quality["accepted"])
    new_state["lastSweep"] = {**quality, "controls": controls}
    new_state["lastSweepAt"] = now
    new_state["lastSweepDate"] = today
    new_state["lastSweepSummary"] = new_state["lastSweep"]
    new_state["requiredObservations"] = {
        key: {**value, "kind": "healthy" if value["classification"] == "ok" else value["classification"]}
        for key, value in observations.items() if key in set(policy.get("requiredMaintainedSources", []))
    }
    if not quality["accepted"]:
        print("::warning::Health sweep inconclusive: counters preserved; observations retained.")
    return quarantined, new_state



def cached_candidates_for_repository(
    upstream: dict,
    cache: dict[tuple[str, str, int], bytes],
    current_entries: dict[str, dict],
    min_app_version_overrides: dict[str, str],
) -> list[dict]:
    """Recover last-known-good selected entries if a legacy index is offline."""
    recovered: list[dict] = []
    for (repository, source_id, version), package in sorted(cache.items()):
        if repository != upstream["name"] or source_id not in current_entries:
            continue
        entry = dict(current_entries[source_id])
        entry["id"] = source_id
        entry["version"] = version
        try:
            recovered.append(
                candidate_from_package(
                    upstream,
                    entry,
                    package,
                    expected_version=version,
                    min_app_version_overrides=min_app_version_overrides,
                )
            )
        except Exception as error:
            print(f"WARNING: unable to recover cached {repository}:{source_id}: {error}")
    return recovered


def _stable_generated_at(inventory: dict, inventory_path: Path, now: str) -> str:
    if not inventory_path.exists():
        return now
    try:
        previous = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return now
    previous_without_time = dict(previous)
    previous_without_time.pop("generatedAt", None)
    current_without_time = dict(inventory)
    current_without_time.pop("generatedAt", None)
    if previous_without_time == current_without_time and previous.get("generatedAt"):
        return str(previous["generatedAt"])
    return now


def validate_catalog_selection(
    selected: list[dict],
    *,
    label: str,
    minimum_count: int,
    previous_effective_ids: set[str],
    required_ids: set[str] | None = None,
    maximum_removal_ratio: float = 0.25,
) -> None:
    ids = [source["id"] for source in selected]
    if len(selected) < minimum_count:
        raise RuntimeError(f"Safety check stopped unexpectedly small {label} catalog: {len(selected)}")
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"Safety check found duplicate IDs in the {label} catalog")
    missing_required = set(required_ids or set()) - set(ids)
    if missing_required:
        raise RuntimeError(f"Safety check found missing required {label} sources: {sorted(missing_required)}")
    previous_count = len(previous_effective_ids)
    removed = previous_effective_ids - set(ids)
    allowed_removals = max(5, int(previous_count * maximum_removal_ratio))
    if previous_count and len(removed) > allowed_removals:
        raise RuntimeError(
            f"Safety check stopped removal of {len(removed)} of {previous_count} {label} sources "
            f"(limit {allowed_removals})"
        )


def write_catalog(
    selected: list[dict],
    duplicates: list[dict],
    catalog_root: Path,
    list_name: str,
    inventory_name: str,
    catalog_policy: str,
    catalog_upstreams: tuple[dict, ...],
) -> None:
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    catalog_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aidoku-refresh-", dir=catalog_root) as temp_name:
        temp = Path(temp_name)
        source_dir = temp / "sources"
        icon_dir = temp / "icons"
        source_dir.mkdir()
        icon_dir.mkdir()

        index_entries = []
        inventory_entries = []
        checksum_lines = []
        for source in selected:
            validate_source_id(source["id"])
            read_package(
                source["package"],
                f"selected source {source['id']}",
                expected_id=source["id"],
                expected_version=source["version"],
            )
            package_name = f"{source['id']}-v{source['version']}.aix"
            icon_name = f"{source['id']}-v{source['version']}.png"
            package_path = source_dir / package_name
            icon_path = icon_dir / icon_name
            package_path.write_bytes(source["package"])
            icon_path.write_bytes(source["icon"])
            digest = hashlib.sha256(source["package"]).hexdigest()
            checksum_lines.append(f"{digest}  sources/{package_name}")

            index_entry = {
                "id": source["id"],
                "name": source["name"],
                "version": source["version"],
                "iconURL": f"icons/{icon_name}",
                "downloadURL": f"sources/{package_name}",
                "languages": source["languages"],
                "contentRating": source["contentRating"],
                "baseURL": source["baseURL"],
            }
            if source["minAppVersion"]:
                index_entry["minAppVersion"] = source["minAppVersion"]
            index_entries.append(index_entry)
            inventory_entries.append(
                {
                    "id": source["id"],
                    "name": source["name"],
                    "version": source["version"],
                    "file": f"sources/{package_name}",
                    "repository": source["repository"],
                    "license": source["license"],
                    "upstreamPackageURL": source["upstreamPackageURL"],
                    "sha256": digest,
                    **{key: source[key] for key in ("provenanceURL", "packageRepository", "sourceCommit", "sourcePath") if key in source},
                }
            )

        source_list = {"name": list_name, "sources": index_entries}
        inventory = {
            "name": inventory_name,
            "sourceCount": len(inventory_entries),
            "catalogPolicy": catalog_policy,
            "languagePolicy": "English or multilingual entries advertising en, All, or multi",
            "excludedPersonalUseOnly": ["en.atsumaru", "multi.mangaball", "multi.onisaga"],
            "replacedWithCommunityBuilds": ["multi.mangadotnet", "multi.kagane"],
            "excludedNonEnglish": ["Non-English-only source packages"],
            "upstreams": [
                {"repository": upstream["name"], "index": upstream["index"], "license": upstream["license"]}
                for upstream in catalog_upstreams
            ],
            "excludedDuplicates": duplicates,
            "sources": inventory_entries,
        }
        inventory["generatedAt"] = _stable_generated_at(
            inventory, catalog_root / "inventory.json", checked_at
        )
        # Keep generatedAt near the top of the human-readable inventory.
        inventory = {
            "name": inventory.pop("name"),
            "generatedAt": inventory.pop("generatedAt"),
            **inventory,
        }

        (temp / "index.min.json").write_text(
            json.dumps(source_list, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        (temp / "index.json").write_text(
            json.dumps(source_list, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (temp / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        for directory in ("sources", "icons"):
            destination = catalog_root / directory
            destination.mkdir(exist_ok=True)
            for old_item in destination.iterdir():
                if old_item.is_dir():
                    shutil.rmtree(old_item)
                else:
                    old_item.unlink()
            for new_item in (temp / directory).iterdir():
                shutil.copy2(new_item, destination / new_item.name)
        for filename in ("index.min.json", "index.json", "inventory.json", "CHECKSUMS.sha256"):
            shutil.move(str(temp / filename), catalog_root / filename)

    readme_path = catalog_root / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8-sig")
        readme = re.sub(
            r"This repository contains \d+ validated `\.aix` packages\.",
            f"This repository contains {len(selected)} validated `.aix` packages.",
            readme,
        )
        readme_path.write_text(readme, encoding="utf-8")
    (catalog_root / ".nojekyll").touch()


def write_rollback_snapshot(path: Path = ROLLBACK_PATH) -> None:
    """Persist the previous published metadata as a bounded rollback checkpoint."""
    inputs = {
        "index": ROOT / "index.min.json",
        "inventory": ROOT / "inventory.json",
        "status": ROOT / "status.json",
    }
    if not all(item.is_file() for item in inputs.values()):
        return
    snapshot = {
        key: json.loads(item.read_text(encoding="utf-8-sig"))
        for key, item in inputs.items()
    }
    previous = None
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
    comparable = dict(previous or {})
    comparable.pop("capturedAt", None)
    if comparable == snapshot:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "capturedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **snapshot,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_health_state_if_changed(state: dict, path: Path = HEALTH_STATE_PATH) -> None:
    text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8-sig") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, prefix="source-health-", suffix=".tmp"
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def write_status_report(
    policy: dict,
    health_state: dict,
    candidates: list[dict],
    maintained: list[dict],
    legacy: list[dict],
    automatic_quarantine: set[str],
) -> None:
    """Publish a compact, human-readable explanation of catalog health."""
    source_metadata: dict[str, dict] = {}
    for candidate in sorted(candidates, key=lambda item: (item["id"], -item["priority"])):
        source_metadata.setdefault(
            candidate["id"],
            {"name": candidate["name"], "baseURL": candidate["baseURL"]},
        )

    manual_entries = []
    for source_id, detail in sorted(policy.get("quarantinedSources", {}).items()):
        metadata = source_metadata.get(source_id, {})
        entry = {
            "id": source_id,
            "name": str(detail.get("name") or metadata.get("name", source_id)),
            "type": "manual",
            "reason": str(detail.get("reason", "Manually quarantined")),
            "catalogs": sorted(as_list(detail.get("catalogs", ["maintained", "legacy"]))),
        }
        if detail.get("issue"):
            entry["issue"] = str(detail["issue"])
        manual_entries.append(entry)

    automatic_entries = []
    degraded_entries = []
    required_ids = set(policy.get("requiredMaintainedSources", []))
    for source_id, record in sorted(health_state.get("sources", {}).items()):
        metadata = source_metadata.get(source_id, {})
        entry = {
            "id": source_id,
            "name": metadata.get("name", source_id),
            "baseURL": metadata.get("baseURL"),
            "status": str(record.get("status", "failing")),
            "consecutiveFailures": int(record.get("consecutiveFailures", 0)),
            "consecutiveSuccesses": int(record.get("consecutiveSuccesses", 0)),
            "lastObservationDate": record.get("lastObservationDate"),
            "required": source_id in required_ids,
            **{key: record[key] for key in ("classification", "httpStatus", "lastProbeAt", "lastStateChangeAt", "severity", "functional") if key in record},
        }
        if source_id in automatic_quarantine:
            automatic_entries.append(entry)
        else:
            degraded_entries.append(entry)

    required_health = []
    for source_id in sorted(required_ids):
        observation = dict(health_state.get("requiredObservations", {}).get(source_id, {}))
        kind = str(observation.get("kind", "unknown"))
        severity = (
            "healthy" if kind == "healthy"
            else "degraded" if observation.get("reachable")
            else "critical" if observation.get("conclusive")
            else "unknown"
        )
        metadata = source_metadata.get(source_id, {})
        required_health.append({
            "id": source_id,
            "name": metadata.get("name", source_id),
            "severity": severity,
            **observation,
        })

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status = {
        "generatedAt": now,
        "summary": {
            "maintained": len(maintained),
            "legacyOnly": len(legacy),
            "manualQuarantined": len(manual_entries),
            "automaticQuarantined": len(automatic_entries),
            "degraded": len(degraded_entries),
            "requiredDegraded": sum(item["severity"] != "healthy" for item in required_health),
        },
        "requiredMaintainedSources": sorted(required_ids),
        "requiredHealth": required_health,
        "healthSweep": {"lastSweepAt": health_state.get("lastHealthSweepAt", health_state.get("lastSweepAt")), "summary": health_state.get("lastSweep", health_state.get("lastSweepSummary", {}))},
        "manualQuarantine": manual_entries,
        "automaticQuarantine": automatic_entries,
        "degraded": degraded_entries,
        "lastHealthSweepAt": health_state.get("lastHealthSweepAt", health_state.get("lastSweepAt")),
        "lastSweep": health_state.get("lastSweep", health_state.get("lastSweepSummary")),
        "websiteChecks": health_state.get("probes", {}),
        "publicAcceptance": {
            "workflowURL": "https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml",
            "resultAuthority": "The post-deployment workflow receipt, not this pre-deployment catalog",
        },
        "functionalAcceptance": {
            "workflowURL": "https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml",
            "resultAuthority": "Pinned-package runtime report; blocked checks are not passes",
        },
    }
    status["generatedAt"] = _stable_generated_at(status, STATUS_JSON_PATH, now)
    status = {"generatedAt": status.pop("generatedAt"), **status}
    json_text = json.dumps(status, ensure_ascii=False, indent=2) + "\n"
    if not STATUS_JSON_PATH.exists() or STATUS_JSON_PATH.read_text(encoding="utf-8-sig") != json_text:
        STATUS_JSON_PATH.write_text(json_text, encoding="utf-8")

    lines = [
        "# Aidoku Source Status",
        "",
        f"Status last changed: {status['generatedAt']}",
        "",
        f"Last website sweep: {health_state.get('lastHealthSweepAt', health_state.get('lastSweepAt')) or 'not recorded by the legacy checker'}",
        "Website reachability, package delivery and chapter reading are separate checks.",
        "[Public feed acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) | [Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml)",
        "",
        f"- Maintained: {len(maintained)}",
        f"- Legacy-only: {len(legacy)}",
        f"- Manually quarantined: {len(manual_entries)}",
        f"- Automatically quarantined: {len(automatic_entries)}",
        f"- Degraded/under observation: {len(degraded_entries)}",
        "",
        "## Quarantined",
        "",
    ]
    if not manual_entries and not automatic_entries:
        lines.append("None.")
    for entry in manual_entries:
        issue = f" ([upstream issue]({entry['issue']}))" if entry.get("issue") else ""
        lines.append(f"- **{entry['name']}** (`{entry['id']}`): {entry['reason']}{issue}")
    for entry in automatic_entries:
        lines.append(
            f"- **{entry['name']}** (`{entry['id']}`): unreachable for "
            f"{entry['consecutiveFailures']} consecutive daily checks"
        )
    lines.extend(["", "## Under observation", ""])
    if not degraded_entries:
        lines.append("None.")
    for entry in degraded_entries:
        protected = "; protected as a required source" if entry["required"] else ""
        lines.append(
            f"- **{entry['name']}** (`{entry['id']}`): {entry['consecutiveFailures']} "
            f"failed sample(s); {entry.get('classification', 'legacy observation')}; last probe {entry.get('lastProbeAt', entry['lastObservationDate'])}{protected}"
        )
    markdown_text = "\n".join(lines) + "\n"
    if not STATUS_MARKDOWN_PATH.exists() or STATUS_MARKDOWN_PATH.read_text(
        encoding="utf-8-sig"
    ) != markdown_text:
        STATUS_MARKDOWN_PATH.write_text(markdown_text, encoding="utf-8")


def main() -> None:
    policy = load_policy()
    manual_maintained = excluded_ids(policy, "maintained")
    manual_legacy = excluded_ids(policy, "legacy")
    excluded_everywhere = manual_maintained & manual_legacy
    cache = build_package_cache((ROOT, ROOT / "legacy"))
    # Force a live check for overrides, but retain their verified cache for
    # outages. A local package must not masquerade as an upstream cache hit.
    override_ids = set(policy.get("localPackageOverrides", {}))
    current_index, _ = load_current(ROOT)
    legacy_index, _ = load_current(ROOT / "legacy")
    min_app_version_overrides = {
        str(source_id): str(version)
        for source_id, version in policy.get("minAppVersionOverrides", {}).items()
    }

    indexed_entries: list[tuple[dict, dict]] = []
    cached_only_candidates: list[dict] = []
    current_entries = {**current_index, **legacy_index}
    for upstream in UPSTREAMS:
        index_host = _safe_https_url(str(upstream["index"]), "upstream index").hostname.casefold()
        try:
            payload = fetch_json(upstream["index"], allowed_hosts={index_host})
        except Exception as error:
            if upstream["name"] == ACTIVE_REPOSITORY:
                raise RuntimeError(f"Active upstream index is unavailable: {error}") from error
            recovered = cached_candidates_for_repository(
                upstream, cache, current_entries, min_app_version_overrides
            )
            if not recovered:
                raise RuntimeError(
                    f"Legacy upstream index is unavailable and has no valid cache: "
                    f"{upstream['name']}: {error}"
                ) from error
            print(
                f"WARNING: {upstream['name']} index failed; retaining "
                f"{len(recovered)} last-known-good source(s): {error}"
            )
            cached_only_candidates.extend(recovered)
            continue
        entries = payload.get("sources", []) if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError(f"{upstream['name']} index sources must be a list")
        english_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and is_english_entry(entry)
            and str(entry.get("id", "")) not in excluded_everywhere
        ]
        print(
            f"{upstream['name']}: {len(english_entries)} eligible English/multilingual index entries"
        )
        indexed_entries.extend((upstream, entry) for entry in english_entries)

    candidates: list[dict] = list(cached_only_candidates)
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        futures = {
            executor.submit(
                candidate_from_entry,
                upstream,
                entry,
                cache,
                min_app_version_overrides,
                upstream["name"] == ACTIVE_REPOSITORY and entry.get("id") in override_ids,
            ): (upstream["name"], entry.get("id", "<unknown>"))
            for upstream, entry in indexed_entries
        }
        for future in concurrent.futures.as_completed(futures):
            repository, source_id = futures[future]
            try:
                candidates.append(future.result())
            except Exception as error:
                message = f"{repository}:{source_id}: {error}"
                errors.append(message)
                print(f"WARNING: skipping invalid source {message}")
    if errors:
        print(f"WARNING: {len(errors)} source package(s) could not be refreshed or recovered")

    candidates = apply_local_package_overrides(candidates, policy)

    required_maintained = set(policy.get("requiredMaintainedSources", []))
    active_health_candidates = [
        candidate
        for candidate in candidates
        if candidate["repository"] == ACTIVE_REPOSITORY
        and candidate["id"] not in manual_maintained
    ]
    automatic_quarantine, health_state = refresh_health_state(active_health_candidates, policy)
    for source_id in manual_maintained:
        health_state.get("sources", {}).pop(source_id, None)
    # Required sources guard against accidental upstream/package disappearance.
    # They are never auto-quarantined by a coarse website reachability probe;
    # a confirmed failure must be handled explicitly in source_policy.json.
    automatic_quarantine -= required_maintained

    active_candidates = [
        candidate
        for candidate in active_health_candidates
        if candidate["id"] not in automatic_quarantine
    ]
    installable_candidates = [
        candidate
        for candidate in candidates
        if candidate["id"] not in manual_legacy
        and candidate["id"] not in automatic_quarantine
    ]
    active_selected, active_duplicates = select_candidates(active_candidates)
    all_selected, all_duplicates = select_candidates(installable_candidates)
    active_ids = {candidate["id"] for candidate in active_selected}
    legacy_selected = [candidate for candidate in all_selected if candidate["id"] not in active_ids]

    if active_ids & {candidate["id"] for candidate in legacy_selected}:
        raise RuntimeError("Safety check found maintained sources duplicated in the legacy delta")
    safety = policy.get("safety", {})
    previous_main_ids = set(current_index)
    previous_legacy_delta_ids = set(legacy_index) - previous_main_ids
    validate_catalog_selection(
        active_selected,
        label="maintained",
        minimum_count=int(safety.get("minimumMaintainedSources", 40)),
        previous_effective_ids=previous_main_ids,
        required_ids=required_maintained,
        maximum_removal_ratio=float(safety.get("maximumRemovalRatio", 0.25)),
    )
    validate_catalog_selection(
        legacy_selected,
        label="legacy",
        minimum_count=int(safety.get("minimumLegacySources", 20)),
        previous_effective_ids=previous_legacy_delta_ids,
        maximum_removal_ratio=float(safety.get("maximumRemovalRatio", 0.25)),
    )

    active_upstreams = tuple(
        upstream for upstream in UPSTREAMS if upstream["name"] == ACTIVE_REPOSITORY
    )
    write_rollback_snapshot()
    write_catalog(
        active_selected,
        active_duplicates,
        ROOT,
        "Nixzle's Maintained English Aidoku Sources",
        "Nixzle's Maintained Public English Aidoku Sources",
        "Packages currently published by the active Aidoku community repository and not quarantined",
        active_upstreams,
    )
    write_catalog(
        legacy_selected,
        all_duplicates,
        ROOT / "legacy",
        "Nixzle's Legacy English Aidoku Sources",
        "Nixzle's Legacy Public English Aidoku Sources",
        "Older unique packages not present in the maintained catalog; these may no longer work",
        UPSTREAMS,
    )
    _write_health_state_if_changed(health_state)
    write_status_report(
        policy,
        health_state,
        candidates,
        active_selected,
        legacy_selected,
        automatic_quarantine,
    )
    print(
        f"Published {len(active_selected)} maintained sources and "
        f"{len(legacy_selected)} unique sources in the legacy catalog"
    )


if __name__ == "__main__":
    main()
