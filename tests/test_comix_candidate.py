import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComixCandidateTests(unittest.TestCase):
    def test_v130_uses_bounded_first_party_webview_navigation(self):
        source_root = ROOT / "source-fixes" / "en.comix"
        manifest = json.loads((source_root / "res" / "source.json").read_text(encoding="utf-8"))
        web = (source_root / "src" / "web.rs").read_text(encoding="utf-8")

        self.assertEqual(manifest["info"]["version"], 130)
        self.assertIn("self.web_view.load(create_request_get(base_url)?)?;", web)
        self.assertNotIn("self.web_view.load_blocking(create_request_get(base_url)?)?;", web)
        self.assertIn("for _ in 0..20", web)
        self.assertNotIn("self.web_view.load_html(&body, Some(base_url))?;", web)
        self.assertIn("WebViewUserScript", web)


if __name__ == "__main__":
    unittest.main()
