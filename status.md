# Aidoku Source Status

Status last changed: 2026-09-26T03:46:59+00:00

Last website sweep: 2026-09-26T03:46:31+00:00
Website reachability, package delivery and chapter reading are separate checks.
[Public feed acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) | [Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml)

- Maintained: 53
- Legacy-only: 47
- Manually quarantined: 4
- Automatically quarantined: 4
- Degraded/under observation: 11

## Quarantined

- **Aqua Manga** (`en.aquamanga`): The site/parser changed and the source needs a rewrite before it is installable again. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/605))
- **Fire Scans** (`en.firescans`): The configured source domain does not currently resolve.
- **Qi Scans** (`en.qiscans`): The configured source domain does not currently resolve.
- **ReadComicOnline** (`en.readcomiconline`): The original ReadComicOnline service has no live domain; use en.readcomicsonline instead. ([upstream issue](https://github.com/Aidoku-Community/sources/issues/639))
- **Hive Scans** (`en.hivescans`): unreachable for 3 consecutive daily checks
- **Manga Sect** (`en.mangasect`): unreachable for 3 consecutive daily checks
- **Manhuagold** (`en.manhuagold`): unreachable for 3 consecutive daily checks
- **Manhwax** (`en.manhwax`): unreachable for 3 consecutive daily checks

## Under observation

- **BatCave** (`en.batcave`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00
- **Elf Toon** (`en.elftoon`): 2 failed sample(s); server_error; last probe 2026-09-26T03:46:31+00:00
- **Madokami** (`en.madokami`): 0 failed sample(s); auth_required; last probe 2026-09-26T03:46:31+00:00
- **MangaTx** (`en.mangatx`): 2 failed sample(s); tls_failure; last probe 2026-09-26T03:46:31+00:00
- **Read Comics Online** (`en.readcomicsonline`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00; protected as a required source
- **WebtoonXYZ** (`en.webtoonxyz`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00
- **Weeb Central** (`en.weebcentral`): 0 failed sample(s); forbidden; last probe 2026-09-26T03:46:31+00:00
- **E-Hentai** (`multi.ehentai`): 0 failed sample(s); restricted; last probe 2026-09-26T03:46:31+00:00
- **Kagane** (`multi.kagane`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00
- **Mangadotnet** (`multi.mangadotnet`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00
- **MyReadingManga** (`multi.myreadingmanga`): 0 failed sample(s); cloudflare_protected; last probe 2026-09-26T03:46:31+00:00
