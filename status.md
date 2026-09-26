# Aidoku Source Status

Status last changed: 2026-09-26T04:05:00+00:00

Checks run daily; this timestamp changes only when catalog or health status changes.

- Maintained: 53
- Legacy-only: 47
- Manually quarantined: 4
- Automatically quarantined: 4
- Degraded/under observation: 2
- Required degraded/unknown: 1
- Last health sweep: 2026-09-26T04:04:33+00:00

## Required source health

- **Comix** (`en.comix`): healthy (healthy)
- **MangaDistrict** (`en.mangadistrict`): healthy (healthy)
- **Read Comics Online** (`en.readcomicsonline`): degraded (protected)

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

- **Elf Toon** (`en.elftoon`): 2 consecutive failed check(s), last observed 2026-09-26
- **MangaTx** (`en.mangatx`): 1 consecutive failed check(s), last observed 2026-09-25
