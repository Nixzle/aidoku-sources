import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComixCandidateTests(unittest.TestCase):
    def test_v132_has_bounded_same_origin_webview_recovery(self):
        source_root = ROOT / "source-fixes" / "en.comix"
        manifest = json.loads((source_root / "res" / "source.json").read_text(encoding="utf-8"))
        web = (source_root / "src" / "web.rs").read_text(encoding="utf-8")
        lib = (source_root / "src" / "lib.rs").read_text(encoding="utf-8")

        settings = (source_root / "res" / "settings.json").read_text(encoding="utf-8")

        self.assertEqual(manifest["info"]["version"], 132)
        self.assertEqual(manifest["info"]["minAppVersion"], "0.9")
        self.assertIn('const COMIX_ORIGINS: &[&str] = &[BASE_URL];', lib)
        self.assertIn('mod transport;', lib)
        self.assertIn('self.web_view.load_html_blocking(SAFE_STUB, Some(BASE_URL))?', web)
        self.assertIn('fn warm_cloudflare_clearance()', web)
        self.assertIn('sleep(15);', web)
        self.assertIn('ReaderRequest::new', web)
        self.assertIn('send_with_view(&self.web_view)', web)
        self.assertIn('Blob([', web)
        self.assertIn('Object.create(null)', web)
        self.assertIn("['__proto__', 'constructor', 'prototype']", web)
        self.assertIn('serde_json::to_string', web)
        self.assertIn('web_view.send_request(&url)?', lib)
        self.assertIn('"key": "connectionMode"', settings)
        self.assertNotIn('self.web_view.load(', web)
        self.assertNotIn('load_blocking(create_request_get', web)


if __name__ == "__main__":
    unittest.main()
