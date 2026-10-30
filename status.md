# Aidoku Source Status

Status last changed: 2026-10-29T19:39:47+00:00

Last website sweep: 2026-10-29T19:39:21+00:00
Website reachability, package delivery and chapter reading are separate checks.
[Public feed acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) | [Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml)

- Maintained: 55
- Legacy-only: 46
- Manually quarantined: 5
- Automatically quarantined: 5
- Degraded/under observation: 7

## Required source health

- **Atsumaru** (`en.atsumaru`): healthy (healthy); reader not certified by reachability
- **Comix WS** (`en.comixws`): healthy (healthy); reader not certified by reachability
- **MangaDistrict** (`en.mangadistrict`): healthy (healthy); reader not certified by reachability
- **Read Comics Online** (`en.readcomicsonline`): degraded (cloudflare_protected); reader not certified by reachability

## Quarantined

- **Aqua Manga** (`en.aquamanga`): The site/parser changed and the source needs a rewrite before it is installable again. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/605))
- **Comix** (`en.comix`): Earlier Nixzle Comix builds failed owner-device acceptance. v139 repairs current page parsing, verification and secure-module discovery; it remains isolated in the dedicated test feed until it passes on the affected iPhone. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/814))
- **Fire Scans** (`en.firescans`): The configured source domain does not currently resolve.
- **Qi Scans** (`en.qiscans`): The configured source domain does not currently resolve.
- **ReadComicOnline** (`en.readcomiconline`): The original ReadComicOnline service has no live domain; use en.readcomicsonline instead. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/639))
- **Madokami** (`en.madokami`): unreachable for 3 consecutive daily checks
- **Manga Sect** (`en.mangasect`): unreachable for 3 consecutive daily checks
- **MangaTx** (`en.mangatx`): unreachable for 3 consecutive daily checks
- **Manhuagold** (`en.manhuagold`): unreachable for 3 consecutive daily checks
- **Manhwax** (`en.manhwax`): unreachable for 3 consecutive daily checks

## Under observation

- **Armageddon** (`en.armageddon`): 0 failed sample(s); forbidden; last probe 2026-10-29T19:39:21+00:00
- **BatCave** (`en.batcave`): 0 failed sample(s); cloudflare_protected; last probe 2026-10-29T19:39:21+00:00
- **Read Comics Online** (`en.readcomicsonline`): 0 failed sample(s); cloudflare_protected; last probe 2026-10-29T19:39:21+00:00; protected as a required source
- **WebtoonXYZ** (`en.webtoonxyz`): 0 failed sample(s); forbidden; last probe 2026-10-29T19:39:21+00:00
- **Weeb Central** (`en.weebcentral`): 0 failed sample(s); forbidden; last probe 2026-10-29T19:39:21+00:00
- **Mangadotnet** (`multi.mangadotnet`): 0 failed sample(s); cloudflare_protected; last probe 2026-10-29T19:39:21+00:00
- **MyReadingManga** (`multi.myreadingmanga`): 0 failed sample(s); cloudflare_protected; last probe 2026-10-29T19:39:21+00:00
