from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts import update_sources as updater


def make_aix(source_id: str = "en.example", version: int = 3) -> bytes:
    manifest = {
        "id": source_id,
        "name": "Example",
        "version": version,
        "languages": ["en"],
        "contentRating": 0,
        "url": "https://example.com",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Payload/source.json", json.dumps(manifest))
        archive.writestr("Payload/main.wasm", b"\x00asm\x01\x00\x00\x00")
        archive.writestr("Payload/icon.png", b"\x89PNG\r\n\x1a\n")
    return output.getvalue()


class UrlSafetyTests(unittest.TestCase):
    def setUp(self):
        self.upstream = {
            "name": "example/repository",
            "asset_base": "https://assets.example/catalog/",
        }

    def test_package_url_rejects_traversal_and_absolute_urls(self):
        for reference in ("../secret.aix", "%2e%2e/secret.aix", "/root.aix", "https://evil.example/aix"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                updater.package_url(self.upstream, {"id": "en.example", "downloadURL": reference})

    def test_package_url_accepts_relative_reference(self):
        self.assertEqual(
            updater.package_url(
                self.upstream,
                {"id": "en.example", "downloadURL": "sources/en.example-v3.aix"},
            ),
            "https://assets.example/catalog/sources/en.example-v3.aix",
        )

    def test_local_reference_stays_inside_legacy_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(
                updater._safe_local_reference(root, "sources/en.example-v3.aix"),
                (root / "sources" / "en.example-v3.aix").resolve(),
            )
            with self.assertRaises(ValueError):
                updater._safe_local_reference(root, "../sources/en.example-v3.aix")

    def test_health_probe_rejects_private_host_without_opening_it(self):
        with mock.patch.object(updater, "_open_url") as open_url:
            self.assertFalse(updater.probe_source_url("https://127.0.0.1/private", attempts=1))
        open_url.assert_not_called()

    def test_redirect_handler_rejects_cross_host_redirect(self):
        handler = updater._SafeRedirectHandler({"assets.example"})
        request = mock.Mock(full_url="https://assets.example/file")
        with self.assertRaises(ValueError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://127.0.0.1/private",
            )

    def test_server_error_does_not_count_as_reachable(self):
        error = updater.urllib.error.HTTPError(
            "https://example.com", 503, "Unavailable", {}, None
        )
        with mock.patch.object(updater, "_is_public_host", return_value=True), mock.patch.object(
            updater, "_open_url", side_effect=error
        ):
            self.assertFalse(updater.probe_source_url("https://example.com", attempts=1))

    def test_cloudflare_error_counts_as_reachable(self):
        error = updater.urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", {}, None
        )
        with mock.patch.object(updater, "_is_public_host", return_value=True), mock.patch.object(
            updater, "_open_url", side_effect=error
        ):
            self.assertTrue(updater.probe_source_url("https://example.com", attempts=1))


class PackageValidationTests(unittest.TestCase):
    def test_valid_aix_is_read(self):
        info, icon = updater.read_package(
            make_aix(), "test", expected_id="en.example", expected_version=3
        )
        self.assertEqual(info["id"], "en.example")
        self.assertTrue(icon.startswith(b"\x89PNG"))

    def test_manifest_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            updater.read_package(make_aix("en.other"), "test", expected_id="en.example")

    def test_invalid_wasm_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "Payload/source.json",
                json.dumps({"id": "en.example", "version": 3}),
            )
            archive.writestr("Payload/main.wasm", b"not-wasm")
            archive.writestr("Payload/icon.png", b"\x89PNG\r\n\x1a\n")
        with self.assertRaisesRegex(ValueError, "WebAssembly"):
            updater.read_package(output.getvalue(), "test")

    def test_archive_traversal_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../escape", b"bad")
            archive.writestr(
                "Payload/source.json",
                json.dumps({"id": "en.example", "version": 3}),
            )
            archive.writestr("Payload/main.wasm", b"\x00asm\x01\x00\x00\x00")
            archive.writestr("Payload/icon.png", b"\x89PNG\r\n\x1a\n")
        with self.assertRaisesRegex(ValueError, "unsafe archive entry"):
            updater.read_package(output.getvalue(), "test")


class CacheTests(unittest.TestCase):
    def test_legacy_cache_is_resolved_against_legacy_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "legacy"
            (legacy / "sources").mkdir(parents=True)
            package = make_aix()
            (legacy / "sources" / "en.example-v3.aix").write_bytes(package)
            (legacy / "index.min.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "en.example",
                                "version": 3,
                                "downloadURL": "sources/en.example-v3.aix",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (legacy / "inventory.json").write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "en.example",
                                "repository": "example/repository",
                                "sha256": updater.hashlib.sha256(package).hexdigest(),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            cache = updater.build_package_cache((legacy,))
            self.assertEqual(cache[("example/repository", "en.example", 3)], package)

    def test_live_failure_uses_validated_last_known_good(self):
        upstream = {
            "name": "example/repository",
            "asset_base": "https://assets.example/catalog/",
            "priority": 1,
            "license": "MIT",
        }
        entry = {
            "id": "en.example",
            "name": "Example",
            "version": 4,
            "languages": ["en"],
            "downloadURL": "sources/en.example-v3.aix",
        }
        package = make_aix()
        with mock.patch.object(updater, "fetch_bytes", side_effect=RuntimeError("offline")):
            candidate = updater.candidate_from_entry(
                upstream,
                entry,
                {("example/repository", "en.example", 3): package},
                {},
            )
        self.assertEqual(candidate["id"], "en.example")
        self.assertEqual(candidate["version"], 3)
        self.assertEqual(candidate["package"], package)

    def test_exact_version_cache_is_immutable_and_skips_download(self):
        upstream = {
            "name": "example/repository",
            "asset_base": "https://assets.example/catalog/",
            "priority": 1,
            "license": "MIT",
        }
        entry = {
            "id": "en.example",
            "name": "Example",
            "version": 3,
            "languages": ["en"],
            "downloadURL": "sources/en.example-v3.aix",
        }
        package = make_aix()
        with mock.patch.object(updater, "fetch_bytes") as fetch:
            candidate = updater.candidate_from_entry(
                upstream,
                entry,
                {("example/repository", "en.example", 3): package},
                {},
            )
        fetch.assert_not_called()
        self.assertEqual(candidate["package"], package)
        self.assertEqual(
            candidate["upstreamPackageURL"],
            "https://assets.example/catalog/sources/en.example-v3.aix",
        )


class HealthStateTests(unittest.TestCase):
    def test_quarantine_after_three_failures_and_recover_after_two_successes(self):
        state = {"version": 1, "sources": {}}
        for day in ("2026-08-10", "2026-08-11", "2026-08-12"):
            state, quarantined = updater.update_health_state(
                state, {"en.example": False}, observation_date=day
            )
        self.assertEqual(quarantined, {"en.example"})
        state, quarantined = updater.update_health_state(
            state, {"en.example": True}, observation_date="2026-08-13"
        )
        self.assertEqual(quarantined, {"en.example"})
        state, quarantined = updater.update_health_state(
            state, {"en.example": True}, observation_date="2026-08-14"
        )
        self.assertEqual(quarantined, set())
        self.assertNotIn("en.example", state["sources"])

    def test_same_day_observation_does_not_advance_counter(self):
        state, _ = updater.update_health_state(
            {"version": 1, "sources": {}},
            {"en.example": False},
            observation_date="2026-08-10",
        )
        state, _ = updater.update_health_state(
            state, {"en.example": False}, observation_date="2026-08-10"
        )
        self.assertEqual(state["sources"]["en.example"]["consecutiveFailures"], 1)

    def test_ongoing_failure_does_not_rewrite_stable_quarantine(self):
        original = {
            "version": 1,
            "sources": {
                "en.example": {
                    "status": "quarantined",
                    "consecutiveFailures": 3,
                    "consecutiveSuccesses": 0,
                    "lastObservationDate": "2026-08-10",
                }
            },
        }
        updated, quarantined = updater.update_health_state(
            original, {"en.example": False}, observation_date="2026-08-11"
        )
        self.assertEqual(updated, original)
        self.assertEqual(quarantined, {"en.example"})

    def test_refresh_does_not_probe_twice_on_a_recorded_day(self):
        today = updater.datetime.now(updater.timezone.utc).date().isoformat()
        state = {
            "version": 1,
            "sources": {
                "en.example": {
                    "status": "failing",
                    "consecutiveFailures": 1,
                    "consecutiveSuccesses": 0,
                    "lastObservationDate": today,
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "health.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            with mock.patch.object(updater, "observe_source_health") as observe:
                quarantined, updated = updater.refresh_health_state([], {}, path)
        observe.assert_not_called()
        self.assertEqual(quarantined, set())
        self.assertEqual(updated, state)

    def test_health_state_is_sorted_deterministically(self):
        state, _ = updater.update_health_state(
            {"version": 1, "sources": {}},
            {"en.zeta": False, "en.alpha": False},
            observation_date="2026-08-10",
        )
        self.assertEqual(list(state["sources"]), ["en.alpha", "en.zeta"])


class SelectionAndDeterminismTests(unittest.TestCase):
    def test_local_override_replaces_older_active_package(self):
        upstream = next(
            item for item in updater.UPSTREAMS if item["name"] == updater.ACTIVE_REPOSITORY
        )
        original_package = make_aix("en.example", 2)
        original = updater.candidate_from_package(
            upstream,
            {"id": "en.example"},
            original_package,
            expected_version=2,
            min_app_version_overrides={},
            upstream_package_url="https://assets.example/en.example-v2.aix",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "overrides").mkdir()
            (root / "overrides" / "en.example-v3.aix").write_bytes(make_aix("en.example", 3))
            policy = {
                "localPackageOverrides": {
                    "en.example": {
                        "path": "overrides/en.example-v3.aix",
                        "provenanceURL": "https://example.com/en.example-v3.aix",
                    }
                }
            }
            result = updater.apply_local_package_overrides([original], policy, root=root)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["version"], 3)
        self.assertEqual(result[0]["repository"], updater.ACTIVE_REPOSITORY)

    def test_local_override_accepts_identical_upstream_version(self):
        upstream = next(
            item for item in updater.UPSTREAMS if item["name"] == updater.ACTIVE_REPOSITORY
        )
        original = updater.candidate_from_package(
            upstream,
            {"id": "en.example"},
            make_aix("en.example", 3),
            expected_version=3,
            min_app_version_overrides={},
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "overrides").mkdir()
            (root / "overrides" / "en.example-v3.aix").write_bytes(original["package"])
            policy = {
                "localPackageOverrides": {
                    "en.example": {
                        "path": "overrides/en.example-v3.aix",
                        "provenanceURL": "https://example.com/en.example-v3.aix",
                    }
                }
            }
            result = updater.apply_local_package_overrides([original], policy, root=root)
            self.assertIs(result[0], original)

    def test_legacy_delta_excludes_maintained_ids(self):
        selected = [
            {"id": "en.active"},
            {"id": "en.legacy"},
        ]
        active_ids = {"en.active"}
        legacy = [candidate for candidate in selected if candidate["id"] not in active_ids]
        self.assertEqual([candidate["id"] for candidate in legacy], ["en.legacy"])

    def test_override_conflict_retains_pinned_bytes_and_other_sources(self):
        upstream = updater.UPSTREAMS[0]
        package = make_aix()
        other = {"id": "en.other", "repository": updater.ACTIVE_REPOSITORY}
        original = updater.candidate_from_package(upstream, {"id": "en.example"},
            package + b"different", expected_version=3, min_app_version_overrides={})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "overrides").mkdir()
            (root / "overrides/example.aix").write_bytes(package)
            policy = {"localPackageOverrides": {"en.example": {
                "path": "overrides/example.aix", "provenanceURL": "https://example.com/pinned"}}}
            result = updater.apply_local_package_overrides([original, other], policy, root=root)
        self.assertIn(other, result)
        self.assertEqual(next(x for x in result if x["id"] == "en.example")["package"], package)

    def test_newer_upstream_retires_override(self):
        original = updater.candidate_from_package(updater.UPSTREAMS[0], {"id": "en.example"},
            make_aix(version=4), expected_version=4, min_app_version_overrides={})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "overrides").mkdir()
            (root / "overrides/example.aix").write_bytes(make_aix())
            policy = {"localPackageOverrides": {"en.example": {
                "path": "overrides/example.aix", "provenanceURL": "https://example.com/pinned"}}}
            self.assertIs(updater.apply_local_package_overrides([original], policy, root=root)[0], original)
            policy["localPackageOverrides"]["en.example"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "Pinned checksum"):
                updater.apply_local_package_overrides([original], policy, root=root)

    def test_override_refresh_checks_live_bytes_but_retains_outage_cache(self):
        upstream = updater.UPSTREAMS[0]
        package = make_aix()
        cache = {(upstream["name"], "en.example", 3): package}
        entry = {"id": "en.example", "version": 3, "downloadURL": "sources/en.example-v3.aix"}
        with mock.patch.object(updater, "fetch_bytes", return_value=package + b"upstream") as fetch:
            result = updater.candidate_from_entry(upstream, entry, cache, {}, True)
            fetch.assert_called_once()
            self.assertNotEqual(result["package"], package)
        with mock.patch.object(updater, "fetch_bytes", side_effect=OSError("offline")):
            result = updater.candidate_from_entry(upstream, entry, cache, {}, True)
            self.assertEqual(result["package"], package)

    def test_generated_at_is_preserved_when_inventory_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "inventory.json"
            path.write_text(
                json.dumps({"name": "Catalog", "generatedAt": "old", "sources": []}),
                encoding="utf-8",
            )
            current = {"name": "Catalog", "sources": []}
            self.assertEqual(updater._stable_generated_at(current, path, "new"), "old")

    def test_manual_policy_quarantines_known_dead_sources(self):
        policy = updater.load_policy()
        for source_id in (
            "en.aquamanga",
            "en.firescans",
            "en.qiscans",
            "en.readcomiconline",
        ):
            self.assertIn(source_id, updater.excluded_ids(policy, "maintained"))
            self.assertIn(source_id, updater.excluded_ids(policy, "legacy"))

    def test_user_requested_sources_are_required(self):
        policy = updater.load_policy()
        self.assertEqual(
            set(policy["requiredMaintainedSources"]),
            {"en.comix", "en.mangadistrict", "en.readcomicsonline"},
        )

    def test_status_report_matches_policy_and_health(self):
        policy = {
            "quarantinedSources": {
                "en.dead": {
                    "name": "Dead Source",
                    "catalogs": ["maintained", "legacy"],
                    "reason": "Offline",
                }
            },
            "requiredMaintainedSources": ["en.example"],
        }
        health = {
            "version": 1,
            "sources": {
                "en.example": {
                    "status": "failing",
                    "consecutiveFailures": 1,
                    "consecutiveSuccesses": 0,
                    "lastObservationDate": "2026-08-10",
                }
            },
        }
        candidate = {
            "id": "en.example",
            "name": "Example",
            "baseURL": "https://example.com",
            "priority": 1,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(updater, "STATUS_JSON_PATH", root / "status.json"), mock.patch.object(
                updater, "STATUS_MARKDOWN_PATH", root / "status.md"
            ):
                updater.write_status_report(policy, health, [candidate], [candidate], [], set())
            report = json.loads((root / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["maintained"], 1)
            self.assertEqual(report["manualQuarantine"][0]["name"], "Dead Source")
            self.assertTrue(report["degraded"][0]["required"])


if __name__ == "__main__":
    unittest.main()
