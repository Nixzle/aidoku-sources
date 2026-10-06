import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import functional_smoke
from scripts import package_reader_fixes


COMIX_SOURCES = {
    "en.comix": 134,
    "en.comixws": 3,
}


class ComixCurrentContractTests(unittest.TestCase):
    def test_current_comix_response_and_image_contract_is_applied(self):
        for source_id, expected_version in COMIX_SOURCES.items():
            with self.subTest(source_id=source_id):
                source = ROOT / "source-fixes" / source_id
                manifest = json.loads((source / "res/source.json").read_text(encoding="utf-8"))
                lib = (source / "src/lib.rs").read_text(encoding="utf-8")
                models = (source / "src/models.rs").read_text(encoding="utf-8")
                web = (source / "src/web.rs").read_text(encoding="utf-8")
                cargo = (source / "Cargo.toml").read_text(encoding="utf-8")

                self.assertEqual(manifest["info"]["version"], expected_version)
                self.assertNotIn("PageImageProcessor", lib)
                self.assertNotIn('header("Referer"', lib)
                self.assertNotIn('header("Origin"', lib)
                self.assertNotIn("base64", cargo)
                self.assertNotIn("pub width:", models)
                self.assertNotIn("pub height:", models)
                self.assertNotIn("pub s:", models)

                self.assertIn("Secure module exports not found", web)
                self.assertIn("module_body", web)
                self.assertNotIn("new Blob", web)
                self.assertIn('else if let Some(enc) = response.get_header("x-enc")', web)
                self.assertIn("let enc_literal = serde_json::to_string(&enc)?;", web)
                self.assertIn("'x-enc': {enc_literal}", web)

        primary = (ROOT / "source-fixes/en.comix/src/lib.rs").read_text(encoding="utf-8")
        websocket = (ROOT / "source-fixes/en.comixws/src/lib.rs").read_text(encoding="utf-8")
        self.assertNotIn("ImageRequestProvider", primary)
        self.assertIn("ImageRequestProvider", websocket)
        self.assertIn("is_allowed_asset_url", websocket)

    def test_home_emits_each_healthy_section_without_waiting_for_all_four(self):
        for source_id in COMIX_SOURCES:
            with self.subTest(source_id=source_id):
                lib = (ROOT / "source-fixes" / source_id / "src/lib.rs").read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("let responses: [Result<Response>; 4]", lib)
                self.assertIn("let mut layout_sent = false;", lib)
                self.assertIn("let mut successful_sections = 0;", lib)
                self.assertIn("send_home_scroller", lib)
                self.assertIn("send_home_recent", lib)
                self.assertIn("if successful_sections == 0", lib)

    def test_chapter_pagination_is_bounded_and_requires_progress(self):
        for source_id in COMIX_SOURCES:
            with self.subTest(source_id=source_id):
                lib = (ROOT / "source-fixes" / source_id / "src/lib.rs").read_text(
                    encoding="utf-8"
                )
                self.assertIn("const MAX_CHAPTER_PAGES", lib)
                self.assertIn("response_page <= previous_response_page", lib)
                self.assertIn("items.is_empty() && response_page < last_page", lib)

    def test_auto_transport_latches_browser_after_first_fallback(self):
        transport = (ROOT / "source-fixes/shared/transport.rs").read_text(encoding="utf-8")
        self.assertIn("send_with_view_observed", transport)
        self.assertIn("prefer_browser", transport)
        self.assertIn("prefer_browser && legacy_fallback", transport)
        for source_id in COMIX_SOURCES:
            web = (ROOT / "source-fixes" / source_id / "src/web.rs").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("sleep(15)", web)
            self.assertNotIn("warm_cloudflare_clearance", web)
            self.assertIn("prefer_browser", web)
            self.assertIn("send_reader_request", web)


class RepositoryStabilityTests(unittest.TestCase):
    def test_required_sources_have_default_functional_cases(self):
        policy = json.loads((ROOT / "config/source_policy.json").read_text(encoding="utf-8"))
        self.assertLessEqual(set(policy["requiredMaintainedSources"]), set(functional_smoke.CASES))
        self.assertEqual(functional_smoke.OPTIONAL_CASES, {"en.comix": "solo"})

    def test_public_acceptance_runs_after_pages_deployment(self):
        workflow = (ROOT / ".github/workflows/public-acceptance.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_run:", workflow)
        self.assertIn('workflows: ["pages build and deployment"]', workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("branches: [main]", workflow)

    def test_reader_cache_restore_precedes_source_build(self):
        workflow = (ROOT / ".github/workflows/reader-fixes.yml").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            workflow.index("Restore reader build cache"),
            workflow.index("Build locked source replacements"),
        )

    def test_same_version_candidate_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            resources = source / "res"
            resources.mkdir(parents=True)
            (resources / "source.json").write_text(
                json.dumps({"info": {"id": "en.test", "version": 7}}),
                encoding="utf-8",
            )
            (resources / "settings.json").write_text("[]", encoding="utf-8")
            wasm = root / "main.wasm"
            wasm.write_bytes(b"new-wasm")
            package = root / "en.test-v7.aix"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("Payload/source.json", (resources / "source.json").read_bytes())
                archive.writestr("Payload/settings.json", b"[]")
                archive.writestr("Payload/main.wasm", b"old-wasm")

            mismatches = package_reader_fixes.package_payload_mismatches(
                package, source, wasm
            )

            self.assertEqual(mismatches, ["Payload/main.wasm"])


if __name__ == "__main__":
    unittest.main()
