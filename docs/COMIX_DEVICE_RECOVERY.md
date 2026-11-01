# Comix recovery after Nixzle v140 failed on the owner iPhone

**Status, 2 November 2026:** The owner reports that Comix v140 did not work
on the affected iPhone. Its precise failure stage and error message have not
been captured. Green CI/package checks do not override this failed
owner-device acceptance. Do not promote v140 to the maintained catalog.

## Recommended: test the original publisher's Yomu Comix source

Yomu independently publishes the Comix source as `en.comix` v138.
Use its original distribution only. Its LICENSE prohibits copying,
rehosting or republishing its package in our catalog.

Official, current source list:
https://smexhy.github.io/yomu-aidoku-sources/comix/index.min.json

Official v138 package:
https://smexhy.github.io/yomu-aidoku-sources/sources/en.comix-v138.aix

On 2 November 2026 the original publisher's feed returned v138.
We verified that its official AIX URL returned HTTP 200, that its ZIP
contained `Payload/source.json` with `id=en.comix`, `version=138`
and minimum Aidoku v0.8.4, and that its `Payload/main.wasm` had the
normal WASM file header. SHA-256 of publisher-hosted download:
`c3993f31de2737788e933e72db89b84a96c37fdeda875d7adc97cd1b2ae80ba4`.

### Safe user-device steps

1. In Aidoku Settings > Backups, export a backup. Preserve it separately.
2. In Settings > Source Lists, remove only our dedicated
   `comix-v132/index.min.json` update-list entry. This action does
   **not** delete an installed source or its library entries. If the
   `reader-candidates` list is also installed, it offers our failed
   v140, so do not tap **Update** for Comix from that list. Keep that
   list if you need its other sources.
3. Add Yomu's original Comix list URL above under Source Lists for
   subsequent updates.
4. In Safari download the original v138 `.aix` link above to Files.
   In Aidoku open Browse > Add Source > **Import Source**, and choose
   that file. Aidoku's `SourceManager.importSource(from:)` replaces the
   installed source directory and source record for the same
   `en.comix` key without requiring the replacement version to be
   higher. It does not invoke a library-clear operation. Do not
   uninstall Comix or delete its library series.
5. Confirm Comix displays **v138** in Browse, then test a previously
   failing chapter in an existing library entry. Do not approve an
   update to our v140 from another still-installed test feed.
6. If chapter access works, verify several existing read markers and
   recent history entries before treating the replacement as accepted.
   Yomu uses different chapter-handling rules and a backup is important.
   If the source still fails or reading history changes unexpectedly,
   preserve the error and restore the backup rather than clearing data.

The publisher explicitly warns that Comix blocks third-party readers.
This may still fail, regardless of source version. It is a replacement
attempt, not certified iPhone success or a permanent bypass. If the
website itself works in Safari, its native reader is the reliable
fallback while finding an authorized source for titles elsewhere.

## Evidence and constraints

- Failed Nixzle source: `en.comix` v140, merged PR #38, publicly
  served from our isolated Comix feed. Build/hash/publication PASS.
  Owner iPhone chapter-reading acceptance FAIL, symptom unspecified.
- Aidoku source implementation:
  https://github.com/Aidoku/Aidoku/blob/main/Aidoku/Core/Sources/SourceManager.swift
  See `importSource(from:)` and `removeSourceList(url:)` for distinct
  source overwrite versus list removal behavior.
- Original Yomu documentation and license:
  https://github.com/Smexhy/yomu-aidoku-sources
- Aidoku community finding:
  https://github.com/Aidoku-Community/sources/issues/814
- Keep our v139/v140 artifact hashes for forensics and rollback. Do not
  ship another higher-numbered Comix candidate without actual iOS
  chapter-rendering evidence. Never copy or mirror Yomu files, cookies,
  access tokens or verification material.
