# Aidoku Source Status

Status last changed: 2026-11-10T20:50:36+00:00

Last website sweep: 2026-11-10T20:50:09+00:00
Website reachability, package delivery and chapter reading are separate checks.
[Public feed acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) | [Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml)

- Maintained: 63
- Legacy-only: 46
- Manually quarantined: 5
- Automatically quarantined: 4
- Degraded/under observation: 11

## Required source health

- **Atsumaru** (`en.atsumaru`): degraded (forbidden); reader not certified by reachability
- **Comix WS** (`en.comixws`): healthy (healthy); reader not certified by reachability
- **MangaDistrict** (`en.mangadistrict`): healthy (healthy); reader not certified by reachability
- **Read Comics Online** (`en.readcomicsonline`): degraded (cloudflare_protected); reader not certified by reachability

## Quarantined

- **Aqua Manga** (`en.aquamanga`): The site/parser changed and the source needs a rewrite before it is installable again. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/605))
- **Comix** (`en.comix`): Comix v140 was published and verified byte-for-byte but failed the owner's iPhone reading acceptance (reported 2026-11-02; exact error not yet captured). Earlier versions also failed. Source remains manually quarantined; do not treat its green CI as chapter success. See docs/COMIX_DEVICE_RECOVERY.md for a publisher-hosted replacement route without deleting the library. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/814))
- **Fire Scans** (`en.firescans`): The configured source domain does not currently resolve.
- **Qi Scans** (`en.qiscans`): The configured source domain does not currently resolve.
- **ReadComicOnline** (`en.readcomiconline`): The original ReadComicOnline service has no live domain; use en.readcomicsonline instead. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/639))
- **Madokami** (`en.madokami`): unreachable for 3 consecutive daily checks
- **Manga Sect** (`en.mangasect`): unreachable for 3 consecutive daily checks
- **MangaTx** (`en.mangatx`): unreachable for 3 consecutive daily checks
- **Manhuagold** (`en.manhuagold`): unreachable for 3 consecutive daily checks

## Under observation

- **Armageddon** (`en.armageddon`): 0 failed sample(s); forbidden; last probe 2026-11-10T20:50:09+00:00
- **Atsumaru** (`en.atsumaru`): 0 failed sample(s); forbidden; last probe 2026-11-10T20:50:09+00:00; protected as a required source
- **BatCave** (`en.batcave`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
- **Novel Archive** (`en.novelarchive`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
- **Raven Scans** (`en.ravenscans`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
- **Read Comics Online** (`en.readcomicsonline`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00; protected as a required source
- **WebtoonXYZ** (`en.webtoonxyz`): 0 failed sample(s); forbidden; last probe 2026-11-10T20:50:09+00:00
- **Weeb Central** (`en.weebcentral`): 0 failed sample(s); forbidden; last probe 2026-11-10T20:50:09+00:00
- **Mangadotnet** (`multi.mangadotnet`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
- **MyReadingManga** (`multi.myreadingmanga`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
- **nhentai** (`multi.nhentai`): 0 failed sample(s); cloudflare_protected; last probe 2026-11-10T20:50:09+00:00
