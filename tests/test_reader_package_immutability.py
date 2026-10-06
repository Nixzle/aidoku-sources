import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scripts import package_reader_fixes as packaging


class ReaderPackageImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "res").mkdir(parents=True)
        (self.source / "res/source.json").write_bytes(b"manifest")
        (self.source / "res/settings.json").write_bytes(b"[]")
        self.wasm = self.root / "main.wasm"
        self.wasm.write_bytes(b"wasm")
        self.package = self.root / "candidate.aix"

    def write_package(self, changed=None, excluded=(), extra=None):
        files = {"Payload/source.json": b"manifest", "Payload/settings.json": b"[]",
                 "Payload/main.wasm": b"wasm"}
        files.update(changed or {})
        files.update(extra or {})
        with zipfile.ZipFile(self.package, "w") as archive:
            for name, data in files.items():
                if name not in excluded:
                    archive.writestr(name, data)

    def test_identical_payload_is_reusable_regardless_of_zip_metadata(self):
        self.write_package(extra={"Payload/": b"", "README.txt": b"not payload"})
        self.assertEqual(packaging.package_payload_mismatches(self.package, self.source, self.wasm), [])

    def test_changed_missing_and_unexpected_payload_are_sorted(self):
        self.write_package(changed={"Payload/main.wasm": b"stale"},
                           excluded=("Payload/settings.json",),
                           extra={"Payload/unexpected.txt": b"unreviewed"})
        self.assertEqual(packaging.package_payload_mismatches(self.package, self.source, self.wasm),
                         ["Payload/main.wasm", "Payload/settings.json", "Payload/unexpected.txt"])

    def test_duplicate_payload_member_is_never_reusable(self):
        self.write_package()
        with zipfile.ZipFile(self.package, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr("Payload/main.wasm", b"wasm")
        self.assertEqual(packaging.package_payload_mismatches(self.package, self.source, self.wasm),
                         ["Payload/main.wasm"])

    def test_same_version_changed_package_is_refused_without_overwriting(self):
        (self.source / "res/source.json").write_text(
            '{"info":{"id":"en.test","version":7,"name":"Test","languages":["en"],'
            '"url":"https://example.com","contentRating":0,"minAppVersion":"0.9"}}')
        output = self.root / "reader-candidates"
        (output / "sources").mkdir(parents=True)
        candidate = output / "sources/en.test-v7.aix"
        self.package = candidate
        self.write_package(changed={"Payload/source.json": (self.source / "res/source.json").read_bytes(),
                                    "Payload/main.wasm": b"old"})
        before = candidate.read_bytes()
        with mock.patch.object(packaging, "ROOT", self.root), \
             mock.patch.object(packaging, "OUTPUT", output), \
             mock.patch.object(packaging, "SOURCES", {"en.test": "test"}), \
             mock.patch.object(packaging, "read_package", return_value=({"version": 7}, b"icon")):
            wasm = self.root / "source-fixes/en.test/target/wasm32-unknown-unknown/release/test.wasm"
            wasm.parent.mkdir(parents=True)
            wasm.write_bytes(b"new")
            source_path = self.root / "source-fixes/en.test/res"
            source_path.mkdir()
            (source_path / "source.json").write_bytes((self.source / "res/source.json").read_bytes())
            (source_path / "settings.json").write_bytes(b"[]")
            with self.assertRaisesRegex(RuntimeError, "[Bb]ump.*version"):
                packaging.main()
        self.assertEqual(candidate.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
