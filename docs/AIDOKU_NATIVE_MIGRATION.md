# Recover Comix titles using Aidoku itself

**Preferred approach (3 November 2026):** Keep Aidoku as the main iPhone reader. For each Comix series, use Aidoku's built-in migration UI to **copy** the series to a working alternative before considering removal of the old entry. Do not install Sanctum Reader or another unofficial Comix package as a prerequisite.

## Before changing anything

1. In **Aidoku → Settings → Backups**, create a new backup including the **Library, History, Chapters, Tracking and Categories**. Export the **.aib** file to Files or another location you control. Confirm the exported file exists. Preserve downloaded chapters separately; library backups are not a substitute for media files.
2. Check the installed Aidoku app version. Version **0.9 (4)** was released on 16 October 2026 with reader fixes, and **0.9** includes the enhanced migration flow and an optional built-in Suwayomi connector.
3. Under **Browse**, install and test alternate content sources from the already available maintained source list: **MangaDex** (`multi.mangadex`) and **Kagane** (`multi.kagane`) are possibilities; **Read Comics Online** (`en.readcomicsonline`) may suit certain western comics. Their catalogue presence is not proof a particular title is available or that chapters render on your device. Do not assume Comix WS avoids Comix's third-party-app restrictions.
4. Keep the original Comix source and old library entries intact while checking replacements. Do not clear cookies, uninstall Aidoku, delete downloaded chapters or remove the source to try to fix a migration.

## Safest migration for one series

1. In Aidoku **Library**, open one series currently attached to the failing Comix source.
2. Open the series **… (more) → Migrate** action.
3. Search an alternate source, inspect its title, language, chapter numbers, chapter coverage and **open a real chapter** before confirming.
4. Choose **Copy**, not the ordinary **Migrate** action. Aidoku's source implementation copies categories and relevant read markers to the destination, **without removing the original library entry or its history**. It maps completed chapters primarily by the highest numbered chapter or volume. That is not a guaranteed one-to-one mapping for specials, alternate numbering, duplicate translations or titles with missing chapters.
5. Return to Library. Confirm **both** entries exist, check the latest chapter/pages and category/tracker state, and read several pages of the replacement inside Aidoku.
6. Only once the replacement passes and the original `.aib` backup is safe should you consider consolidating duplicates. Aidoku v0.9 exposes **Migrate and Keep History**, which handles history differently from the plain **Migrate** action. Do not run a bulk migration without matching and checking every title.

## Additional titles

Aidoku has a **Browse → Migrate Sources** screen for source-level migration. Prefer starting with one or two representative titles, then use the bulk flow only if matches and chapter mapping are correct. Skip unmatched series instead of inventing source equivalents. A title absent from alternative catalogues cannot be made available by moving a bookmark.

## PC and iPhone continuity

Suwayomi is **optional**, not required for Aidoku-native source migration. Aidoku v0.9 can connect to a Suwayomi server, but the server must be installed, configured, running and supplied with working content sources. It does **not** bypass Comix's source restrictions or automatically merge all existing Aidoku and Suwayomi libraries. Remote access requires deliberate network security.

For reading progress that should follow between providers, an external tracker such as AniList can sometimes help at **series/chapter level**, but this is not a guaranteed page-perfect or library-perfect synchronization system.

## Verified evidence and limits

- Official Aidoku v0.9 release notes: https://aidoku.app/release-notes/v0.9/
- Current Aidoku release: https://github.com/Aidoku/Aidoku/releases/tag/v0.9-4
- Aidoku's built-in migration code: https://github.com/Aidoku/Aidoku/blob/main/Aidoku/Core/Library/Services/MangaManager.swift
- Built-in single-series migration choices: https://github.com/Aidoku/Aidoku/blob/main/Aidoku/Features/Migration/MigrateSingleSearchView.swift
- Published maintained source list: https://nixzle.github.io/aidoku-sources/index.min.json
- Quarantined Nixzle Comix v140: see [Comix incident recovery](COMIX_DEVICE_RECOVERY.md).

**Not yet verified:** the actual iPhone's Aidoku version, exported owner library, specific title matches, image rendering and a successful owner-device migration. No library modifications have been performed remotely.
