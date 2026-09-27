# Aidoku Source Status

Status last changed: 2026-09-27T15:01:21+00:00

Last website sweep: 2026-09-27T15:00:54+00:00
Website reachability, package delivery and chapter reading are separate checks.
[Public feed acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) | [Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml)

- Maintained: 52
- Legacy-only: 47
- Manually quarantined: 5
- Automatically quarantined: 4
- Degraded/under observation: 10

## Required source health

- **MangaDistrict** (`en.mangadistrict`): healthy (healthy); reader not certified by reachability
- **Read Comics Online** (`en.readcomicsonline`): degraded (cloudflare_protected); reader not certified by reachability

## Quarantined

- **Aqua Manga** (`en.aquamanga`): The site/parser changed and the source needs a rewrite before it is installable again. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/605))
- **Comix** (`en.comix`): Nixzle v127/v128 failed owner-device acceptance on the affected Aidoku Cloudflare client. Do not advertise these builds as reliable. Use a separately maintained Comix implementation with full WebView page-image/cover handling until the app image transport is fixed. ([upstream issue](https://github.com/Aidoku/Aidoku/issues/1034))
- **Fire Scans** (`en.firescans`): The configured source domain does not currently resolve.
- **Qi Scans** (`en.qiscans`): The configured source domain does not currently resolve.
- **ReadComicOnline** (`en.readcomiconline`): The original ReadComicOnline service has no live domain; use en.readcomicsonline instead. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/639))
- **Hive Scans** (`en.hivescans`): unreachable for 3 consecutive daily checks
- **Manga Sect** (`en.mangasect`): unreachable for 3 consecutive daily checks
- **Manhuagold** (`en.manhuagold`): unreachable for 3 consecutive daily checks
- **Manhwax** (`en.manhwax`): unreachable for 3 consecutive daily checks

## Under observation

- **Armageddon** (`en.armageddon`): 0 failed sample(s); forbidden; last probe 2026-09-27T15:00:54+00:00
- **BatCave** (`en.batcave`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-27T15:00:54+00:00
- **Madokami** (`en.madokami`): 0 failed sample(s); auth_required; last probe 2026-09-27T15:00:54+00:00
- **MangaTx** (`en.mangatx`): 2 failed sample(s); tls_failure; last probe 2026-09-27T15:00:54+00:00
- **Read Comics Online** (`en.readcomicsonline`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-27T15:00:54+00:00; protected as a required source
- **WebtoonXYZ** (`en.webtoonxyz`): 0 failed sample(s); forbidden; last probe 2026-09-27T15:00:54+00:00
- **Weeb Central** (`en.weebcentral`): 0 failed sample(s); forbidden; last probe 2026-09-27T15:00:54+00:00
- **Kagane** (`multi.kagane`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-27T15:00:54+00:00
- **Mangadotnet** (`multi.mangadotnet`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-27T15:00:54+00:00
- **MyReadingManga** (`multi.myreadingmanga`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-27T15:00:54+00:00
