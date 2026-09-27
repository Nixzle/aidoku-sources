import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ComixCandidateTests(unittest.TestCase):
    def test_v131_uses_aidoku_native_cloudflare_path(self):
        source_root = ROOT / "source-fixes" / "en.comix"
        manifest = json.loads((source_root / "res" / "source.json").read_text(encoding="utf-8"))
        web = (source_root / "src" / "web.rs").read_text(encoding="utf-8")
        lib = (source_root / "src" / "lib.rs").read_text(encoding="utf-8")

        self.assertEqual(manifest["info"]["version"], 131)
        self.assertEqual(manifest["info"]["minAppVersion"], "0.9")
        self.assertIn("let response = request.send()?;", web)
        self.assertIn("self.web_view.load_html_blocking(", web)
        self.assertIn("let response = web_view.build_request(&url)?.send()?;", lib)
        self.assertNotIn("send_with_view", web)
        self.assertNotIn("mod transport;", lib)


if __name__ == "__main__":
    unittest.main()
