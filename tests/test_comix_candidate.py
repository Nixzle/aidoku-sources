import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComixCandidateTests(unittest.TestCase):
    def test_v134_has_bounded_same_origin_webview_recovery(self):
        source_root = ROOT / "source-fixes" / "en.comix"
        manifest = json.loads((source_root / "res" / "source.json").read_text(encoding="utf-8"))
        web = (source_root / "src" / "web.rs").read_text(encoding="utf-8")
        lib = (source_root / "src" / "lib.rs").read_text(encoding="utf-8")
        settings = (source_root / "res" / "settings.json").read_text(encoding="utf-8")

        self.assertEqual(manifest["info"]["version"], 134)
        self.assertEqual(manifest["info"]["minAppVersion"], "0.9")
        self.assertIn('const COMIX_ORIGINS: &[&str] = &[BASE_URL];', lib)
        self.assertIn('mod transport;', lib)
        self.assertIn('self.web_view.load_html_blocking(SAFE_STUB, Some(BASE_URL))?', web)
        self.assertIn('fn send_reader_request', web)
        self.assertIn('prefer_browser', web)
        self.assertNotIn('sleep(15);', web)
        self.assertIn('ReaderRequest::new', web)
        self.assertIn('send_with_view_observed', web)
        self.assertNotIn('new Blob', web)
        self.assertIn('Secure module exports not found', web)
        self.assertIn('Object.create(null)', web)
        self.assertIn("['__proto__', 'constructor', 'prototype']", web)
        self.assertIn('serde_json::to_string', web)
        self.assertIn('const MODULE_TOKEN: &str = "__AIDOKU_COMIX_MODULE__";', web)
        self.assertIn("const vmKey = '__AIDOKU_COMIX_MODULE__';", web)
        self.assertIn("!key.startsWith('vm')", web)
        self.assertIn('candidates.length !== 1', web)
        self.assertNotIn('window.vm = await import', web)
        self.assertIn('web_view.send_request(&url)?', lib)
        self.assertIn('"key": "connectionMode"', settings)
        self.assertNotIn('self.web_view.load(', web)
        self.assertNotIn('load_blocking(create_request_get', web)

    def test_comix_ws_is_independent_and_host_bounded(self):
        source_root = ROOT / "source-fixes" / "en.comixws"
        manifest = json.loads((source_root / "res" / "source.json").read_text(encoding="utf-8"))
        lib = (source_root / "src" / "lib.rs").read_text(encoding="utf-8")
        settings = (source_root / "res" / "settings.json").read_text(encoding="utf-8")

        self.assertEqual(manifest["info"]["id"], "en.comixws")
        self.assertEqual(manifest["info"]["name"], "Comix WS")
        self.assertEqual(manifest["info"]["version"], 3)
        self.assertEqual(manifest["info"]["url"], "https://comix.ws")
        self.assertIn('const BASE_URL: &str = "https://comix.ws";', lib)
        self.assertIn('"https://static.comix.ws/"', lib)
        self.assertIn('Rejected unexpected Comix WS image host', lib)
        self.assertNotIn('header("Referer"', lib)
        self.assertNotIn('header("Origin"', lib)
        self.assertNotIn('https://comix.to', lib)
        self.assertIn('https://comix.ws/@waf/challenge?return=/', settings)


if __name__ == "__main__":
    unittest.main()
