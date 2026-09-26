from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile
from unittest import mock

from scripts import critical_smoke, public_acceptance


def make_aix(source_id="en.example", version=1):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Payload/source.json", json.dumps({"id": source_id, "version": version}))
        archive.writestr("Payload/main.wasm", b"\x00asm")
        archive.writestr("Payload/icon.png", b"\x89PNG")
    return output.getvalue()


class CriticalSmokeTests(unittest.TestCase):
    def test_required_chapter_smoke_passes_on_expected_markers(self):
        policy = {
            "requiredMaintainedSources": ["en.example"],
            "criticalSmokeTests": {
                "en.example": {
                    "url": "https://example.com/chapter-1",
                    "requiredSubstrings": ["Page 1"],
                    "level": "chapter",
                }
            },
        }
        with mock.patch.object(critical_smoke, "fetch", return_value=(200, b"Page 1")):
            report = critical_smoke.run(policy)
        self.assertEqual(report["result"], "pass")

    def test_protected_endpoint_is_degraded_not_falsely_healthy(self):
        policy = {
            "requiredMaintainedSources": ["en.example"],
            "criticalSmokeTests": {
                "en.example": {
                    "url": "https://example.com/chapter-1",
                    "requiredSubstrings": ["Page 1"],
                    "allowProtected": True,
                }
            },
        }
        with mock.patch.object(critical_smoke, "fetch", return_value=(403, b"challenge")):
            report = critical_smoke.run(policy)
        self.assertEqual(report["result"], "degraded")
        self.assertEqual(report["sources"][0]["result"], "protected")

    def test_missing_parser_marker_fails(self):
        policy = {
            "requiredMaintainedSources": ["en.example"],
            "criticalSmokeTests": {
                "en.example": {
                    "url": "https://example.com/chapter-1",
                    "requiredSubstrings": ["reader-pages"],
                }
            },
        }
        with mock.patch.object(critical_smoke, "fetch", return_value=(200, b"layout changed")):
            report = critical_smoke.run(policy)
        self.assertEqual(report["result"], "fail")

    def test_timeout_is_degraded_not_a_runner_crash(self):
        policy = {
            "requiredMaintainedSources": ["en.example"],
            "criticalSmokeTests": {
                "en.example": {
                    "url": "https://example.com/chapter-1",
                    "requiredSubstrings": ["Page 1"],
                    "allowProtected": True,
                }
            },
        }
        with mock.patch.object(critical_smoke, "fetch", side_effect=TimeoutError("timed out")):
            report = critical_smoke.run(policy)
        self.assertEqual(report["result"], "degraded")
        self.assertEqual(report["sources"][0]["result"], "inconclusive")


class PublicAcceptanceTests(unittest.TestCase):
    def test_public_package_checksum_and_manifest_are_verified(self):
        package = make_aix()
        source = {"id": "en.example", "version": 1, "downloadURL": "sources/en.example-v1.aix"}
        inventory = {"sha256": hashlib.sha256(package).hexdigest()}
        with mock.patch.object(public_acceptance, "fetch", return_value=package):
            result = public_acceptance.verify_package(
                source, inventory, "https://example.github.io/repo/"
            )
        self.assertEqual(result["id"], "en.example")

    def test_public_package_checksum_mismatch_fails(self):
        package = make_aix()
        source = {"id": "en.example", "version": 1, "downloadURL": "sources/en.example-v1.aix"}
        with mock.patch.object(public_acceptance, "fetch", return_value=package):
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                public_acceptance.verify_package(
                    source, {"sha256": "0" * 64}, "https://example.github.io/repo/"
                )


if __name__ == "__main__":
    unittest.main()
