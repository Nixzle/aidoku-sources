from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import publication
from scripts import update_sources as updater


def make_package(version=3, extra=b''):
    stream = io.BytesIO()
    manifest = {'info': {'id': 'en.example', 'name': 'Example', 'version': version,
                        'languages': ['en'], 'url': 'https://example.com', 'contentRating': 0}}
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, data in [('Payload/source.json', json.dumps(manifest).encode()),
                           ('Payload/main.wasm', b'\x00asm\x01\x00\x00\x00' + extra),
                           ('Payload/icon.png', b'\x89PNG\r\n\x1a\n'),
                           ('Payload/settings.json', b'[{"key":"setting","default":true}]')]:
            archive.writestr(zipfile.ZipInfo(name, (2026, 9, 26, 0, 0, 0)), data)
    return stream.getvalue()


def candidate(version=3, extra=b''):
    return updater.candidate_from_package(updater.UPSTREAMS[0], {'id': 'en.example'},
        make_package(version, extra), expected_version=version, min_app_version_overrides={},
        upstream_package_url=f'https://aidoku-community.github.io/sources/sources/en.example-v{version}.aix')


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = {'republishedSources': {'en.example': {
            'minimumPublishedVersion': 4, 'reason': 'Same-version correction delivery'}}}

    def apply(self, item):
        return publication.apply([item], self.policy, root=self.root, updater=updater)[0]

    def remember(self, item):
        filename = f'sources/{item["id"]}-v{item["version"]}.aix'
        (self.root / 'sources').mkdir(exist_ok=True)
        (self.root / filename).write_bytes(item['package'])
        entry = {'id': item['id'], 'version': item['version'], 'downloadURL': filename}
        inventory = {'id': item['id'], 'version': item['version'], 'file': filename,
                     'sha256': hashlib.sha256(item['package']).hexdigest(),
                     'repository': item['repository'], 'upstreamPackageURL': item['upstreamPackageURL'],
                     **{key: item[key] for key in publication.FIELDS if key in item}}
        (self.root / 'index.min.json').write_text(json.dumps({'sources': [entry]}))
        (self.root / 'inventory.json').write_text(json.dumps({'sources': [inventory]}))
        return inventory

    def test_update_is_detectable_and_only_manifest_version_changes(self):
        original = candidate()
        self.remember(original)
        published = self.apply(original)
        self.assertGreater(published['version'], original['version'])
        self.assertEqual(published['version'], 4)
        self.assertEqual(published['id'], original['id'])
        self.assertEqual(published['upstreamVersion'], 3)
        self.assertEqual(published['upstreamSha256'], hashlib.sha256(original['package']).hexdigest())
        with zipfile.ZipFile(io.BytesIO(original['package'])) as before, zipfile.ZipFile(io.BytesIO(published['package'])) as after:
            self.assertEqual(before.namelist(), after.namelist())
            for name in before.namelist():
                if name == 'Payload/source.json':
                    old, new = json.loads(before.read(name)), json.loads(after.read(name))
                    self.assertEqual(new['info']['version'], 4)
                    new['info']['version'] = 3
                    self.assertEqual(old, new)
                else:
                    self.assertEqual(before.read(name), after.read(name), name)

    def test_unchanged_upstream_does_not_increment_or_change_bytes(self):
        published = self.apply(candidate())
        self.remember(published)
        repeated = self.apply(candidate())
        self.assertEqual(published, repeated)

    def test_cached_published_package_does_not_increment_during_outage(self):
        published = self.apply(candidate())
        self.remember(published)
        cached = updater.candidate_from_package(updater.UPSTREAMS[0], {'id': 'en.example'},
            published['package'], expected_version=4, min_app_version_overrides={},
            upstream_package_url='https://example.com/wrong-cache-url')
        restored = self.apply(cached)
        self.assertEqual(restored['version'], 4)
        self.assertEqual(restored['package'], published['package'])
        self.assertEqual(restored['upstreamPackageURL'], published['upstreamPackageURL'])
        self.assertEqual(restored['upstreamSha256'], published['upstreamSha256'])

    def test_upstream_version_collision_remains_detectable(self):
        self.remember(self.apply(candidate()))
        next_release = self.apply(candidate(4, b'new'))
        self.assertEqual(next_release['upstreamVersion'], 4)
        self.assertEqual(next_release['version'], 5)

    def test_changed_bytes_at_same_upstream_version_increment_client(self):
        self.remember(self.apply(candidate()))
        changed = self.apply(candidate(3, b'repaired'))
        self.assertEqual(changed['version'], 5)
        self.assertEqual(changed['upstreamVersion'], 3)
        self.remember(changed)
        self.assertEqual(self.apply(candidate(3, b'repaired')), changed)

    def test_much_newer_upstream_keeps_its_version_when_sufficient(self):
        self.remember(self.apply(candidate()))
        self.assertEqual(self.apply(candidate(12))['version'], 12)

    def test_unconfigured_and_other_repository_sources_are_untouched(self):
        original = candidate()
        self.assertIs(publication.apply([original], {}, root=self.root, updater=updater)[0], original)
        original['repository'] = 'other/repository'
        self.assertIs(self.apply(original), original)

    def test_invalid_policy_rejected(self):
        for value in [True, 0, -1, '4', 2**31]:
            self.policy['republishedSources']['en.example']['minimumPublishedVersion'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                publication.validate_policy(self.policy)
        self.policy['republishedSources']['en.example']['minimumPublishedVersion'] = 4
        self.policy['localPackageOverrides'] = {'en.example': {}}
        with self.assertRaises(ValueError):
            publication.validate_policy(self.policy)

    def test_versioned_cache_identity_cannot_skip_live_upstream(self):
        source = Path(updater.__file__).read_text(encoding='utf-8')
        self.assertIn('override_ids | refresh_cached_ids | revision_ids', source)

    def test_published_provenance_is_checked(self):
        published = self.apply(candidate())
        inventory = self.remember(published)
        publication.validate_record(inventory, published['package'])
        for key, invalid in [('upstreamVersion', 999), ('upstreamSha256', 'broken'),
                             ('upstreamWasmSha256', '0' * 64), ('publicationTransform', 'unknown')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                publication.validate_record({**inventory, key: invalid}, published['package'])


if __name__ == '__main__':
    unittest.main()
