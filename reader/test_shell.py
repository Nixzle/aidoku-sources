import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "reader"

class SanctumReaderShellTests(unittest.TestCase):
    def test_all_local_files_exist(self):
        required = [
            "index.html", "style.css", "app.mjs", "core.mjs", "plist.mjs",
            "cbz.mjs", "sw.js", "manifest.webmanifest", "icon.svg",
            "test-fixtures/sample.aib", "test-fixtures/sample.cbz",
        ]
        self.assertTrue(all((READER / name).is_file() for name in required))

    def test_explicit_privacy_and_user_control(self):
        page = (READER / "index.html").read_text(encoding="utf-8")
        script = (READER / "app.mjs").read_text(encoding="utf-8")
        for control in ["importAidoku", "exportBtn", "importJsonBtn", "openCbz", "cbzFile", "progressDialog", "cbzDialog"]:
            self.assertIn('id="' + control + '"', page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("No scraping", page)
        self.assertIn("indexedDB", script)
        self.assertIn("sourceFilter", script)
        self.assertNotIn("localStorage.setItem('token'", script)
        self.assertNotIn('document.cookie', script)

    def test_service_worker_is_app_only(self):
        sw = (READER / "sw.js").read_text(encoding="utf-8")
        self.assertIn('url.origin !== self.location.origin', sw)
        self.assertIn('request.method !== "GET"', sw)
        self.assertNotIn("https://comix.to", sw)
        self.assertIn('./cbz.mjs', sw)

    def test_no_unreviewed_remote_scripts(self):
        page = (READER / "index.html").read_text(encoding="utf-8")
        self.assertIn('type="module" src="./app.mjs"', page)
        self.assertNotIn('src="https://', page)
        self.assertNotIn("fetch(", (READER / "app.mjs").read_text(encoding="utf-8"))
