import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import package_reader_fixes as packager


class ReaderPackageSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'reader-candidates'
        self.output.mkdir()
        self.entries = []
        self.inventory = []
        self.enterContext(mock.patch.object(packager, 'ROOT', self.root))
        self.enterContext(mock.patch.object(packager, 'OUTPUT', self.output))
        self.enterContext(mock.patch.dict(os.environ, {'GITHUB_SHA': 'a' * 40}))
        self.package_reader = self.enterContext(
            mock.patch.object(packager, 'read_package', side_effect=self.read_test_package)
        )

    @staticmethod
    def read_test_package(data, source_id, *, expected_id, expected_version):
        # Selection tests exercise real ZIP bytes; format validation has its own tests.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = json.loads(archive.read('Payload/source.json'))['info']
            if info['id'] != expected_id or info['version'] != expected_version:
                raise ValueError('Unexpected package identity')
            return info, archive.read('Payload/icon.png')

    def make_source(self, source_id, version):
        source = self.root / 'source-fixes' / source_id
        resources = source / 'res'
        resources.mkdir(parents=True)
        info = {
            'id': source_id, 'name': source_id, 'version': version,
            'languages': ['en'], 'url': 'https://example.invalid',
            'contentRating': 1, 'minAppVersion': '0.9',
        }
        (resources / 'source.json').write_text(json.dumps({'info': info}), encoding='utf-8')
        (resources / 'settings.json').write_text('[]', encoding='utf-8')
        (resources / 'icon.png').write_bytes(b'test-icon')
        wasm = source / 'target/wasm32-unknown-unknown/release' / (packager.SOURCES[source_id] + '.wasm')
        wasm.parent.mkdir(parents=True)
        wasm.write_bytes(b'\x00asm\x01\x00\x00\x00' + source_id.encode())
        return wasm

    def preserve_candidate(self, source_id, version):
        package_name = f'sources/{source_id}-v{version}.aix'
        icon_name = f'icons/{source_id}-v{version}.png'
        for name, data in [(package_name, b'unchanged-package-' + source_id.encode()),
                           (icon_name, b'unchanged-icon-' + source_id.encode())]:
            target = self.output / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
        entry = {
            'id': source_id, 'name': source_id, 'version': version,
            'downloadURL': package_name, 'iconURL': icon_name,
            'languages': ['en'], 'baseURL': 'https://example.invalid',
            'contentRating': 1, 'minAppVersion': '0.9',
            'retainedField': 'keep this entry intact',
        }
        item = {
            'id': source_id, 'version': version, 'file': package_name,
            'sha256': hashlib.sha256((self.output / package_name).read_bytes()).hexdigest(),
            'wasmSha256': 'b' * 64, 'sourceCommit': 'c' * 40,
            'provenanceURL': 'https://example.invalid/original-provenance',
            'acceptance': 'Original acceptance marker',
        }
        self.entries.append(entry)
        self.inventory.append(item)
        (self.output / 'index.json').write_text(json.dumps({'name': 'Candidates', 'sources': self.entries}), encoding='utf-8')
        (self.output / 'inventory.json').write_text(json.dumps({'sourceCount': len(self.inventory), 'sources': self.inventory}), encoding='utf-8')
        return entry, item

    def package(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            packager.main(*args)

    def read_inventory(self):
        return json.loads((self.output / 'inventory.json').read_text())['sources']

    def test_selected_comix_preserves_other_entries_files_and_provenance(self):
        self.make_source('en.comix', 139)
        kept = [self.preserve_candidate('en.comixws', 3),
                self.preserve_candidate('en.asurascans', 20)]
        self.preserve_candidate('en.comix', 134)
        preserved_files = {
            name: ((self.output / name).read_bytes(), (self.output / name).stat().st_mtime_ns)
            for entry, _ in kept for name in [entry['downloadURL'], entry['iconURL']]
        }
        self.package(['en.comix'])
        entries = {row['id']: row for row in json.loads((self.output / 'index.json').read_text())['sources']}
        inventory = {row['id']: row for row in self.read_inventory()}
        self.assertEqual(entries['en.comix']['version'], 139)
        self.assertEqual(set(entries), {'en.comix', 'en.comixws', 'en.asurascans'})
        for entry, item in kept:
            self.assertEqual(entries[entry['id']], entry)
            self.assertEqual(inventory[item['id']], item)
        for name, expected in preserved_files.items():
            target = self.output / name
            self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), expected)
        self.assertFalse((self.root / 'source-fixes/en.comixws').exists())
        self.assertFalse((self.root / 'overrides').exists())
        self.assertEqual({call.args[1] for call in self.package_reader.call_args_list}, {'en.comix'})
        checksums = (self.output / 'CHECKSUMS.sha256').read_text()
        for item in inventory.values():
            self.assertIn(item['sha256'] + '  ' + item['file'] + '\n', checksums)

    def test_default_main_packages_all_sources_without_reading_unittest_arguments(self):
        for source_id in packager.SOURCES:
            self.make_source(source_id, 7)
        with mock.patch('sys.argv', ['unittest', '-v', '--unexpected-test-argument']):
            self.package()
        self.assertEqual({row['id'] for row in self.read_inventory()}, set(packager.SOURCES))
        self.assertTrue((self.root / 'overrides/en.comixws-v7.aix').is_file())

    def test_identical_selected_package_retains_original_build_provenance(self):
        self.make_source('en.comix', 139)
        self.package(['en.comix'])
        before = self.read_inventory()[0]
        target = self.output / before['file']
        package_bytes = target.read_bytes()
        with mock.patch.dict(os.environ, {'GITHUB_SHA': 'd' * 40}):
            self.package(['en.comix'])
        self.assertEqual(self.read_inventory()[0], before)
        self.assertEqual(before['sourceCommit'], 'a' * 40)
        self.assertEqual(target.read_bytes(), package_bytes)

    def test_changed_same_version_payload_is_rejected_without_overwrite(self):
        wasm = self.make_source('en.comix', 139)
        self.package(['en.comix'])
        item = self.read_inventory()[0]
        target = self.output / item['file']
        package_bytes = target.read_bytes()
        inventory_bytes = (self.output / 'inventory.json').read_bytes()
        wasm.write_bytes(b'changed-wasm')
        with self.assertRaisesRegex(RuntimeError, 'differs.*bump the source version'):
            self.package(['en.comix'])
        self.assertEqual(target.read_bytes(), package_bytes)
        self.assertEqual((self.output / 'inventory.json').read_bytes(), inventory_bytes)

    def test_incomplete_unselected_catalogue_is_rejected_before_packaging(self):
        self.make_source('en.comix', 139)
        self.preserve_candidate('en.asurascans', 20)
        (self.output / 'inventory.json').write_text('{"sources":[]}', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'feed and inventory IDs differ'):
            self.package(['en.comix'])
        self.assertFalse((self.output / 'sources/en.comix-v139.aix').exists())

    def test_unknown_or_empty_selection_is_rejected(self):
        for selection in [[], ['en.unknown']]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.package(selection)


if __name__ == '__main__':
    unittest.main()
