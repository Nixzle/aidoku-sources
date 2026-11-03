# Sanctum Reader v1

A static, local-first bookshelf at `https://nixzle.github.io/aidoku-sources/reader/`.

**Purpose:** recover library entries and last-read positions from a user-exported Aidoku `.aib` backup, open first-party reading links, maintain manual progress, and export/import a portable JSON catalogue on Windows and iOS. This does not require Comix's unofficial APIs and never scrapes, downloads, decodes or republishes its pages.

**Import flow:** Aidoku → Settings → Backups → create backup with library/history/chapters → long press → Export → Save to Files. On Sanctum Reader, choose Import Aidoku backup, select that file, and review the extracted titles. The backup is parsed by the browser only. IndexedDB retains only the sanitized metadata: title, source ID, safe URL, last chapter/page, dates and notes. Binary blobs and settings/cookies are discarded. The original file stays unchanged. Keep the original Aidoku backup.

**Cross-device:** Comix's own account syncs reading activity within its website, subject to its availability and permissions. Sanctum Reader's library metadata is **per device**; export JSON, transfer, and import it on a second device for a manual merge. There is no hidden cloud sync, and no request for account tokens. This is deliberate until an authorized, secure backend is configured. Metadata may be cleared by browser-storage eviction; keep a JSON backup.

**Offline:** the static app shell loads offline after a successful installation. The external reading websites still require a network connection and may fail or restrict service. This app does not bypass protection. Local CBZ/ZIP files containing user-owned image pages can be read directly in the browser with native ZIP decompression, without upload or permanent media storage. The selected file must be reopened on a later visit; its page position is stored as metadata. Automatic cross-device metadata sync is not implemented.

**Privacy and safety:** zero telemetry, zero server-side upload, no third-party JS dependencies, strict URL sanitizing, CSP, local-only IndexedDB, explicit user export. Avoid uploading `.aib` files to unknown websites, as they may contain sensitive settings.

**Testing:** `node --test reader/*.test.mjs` validates binary plist parsing (including generated Aidoku-style fixtures), extraction, malicious URL rejection, versioned export/import, merge semantics and regression rules. The static shell is independently validated by `reader/test_shell.py`.

**Known limitations:** Direct chapter image rendering in Aidoku is not repaired; Comix may block third-party apps. Chapter web URLs are used only if present in the backup. Some source-specific URL formats may require manually correcting a reading link. No claim of successful iPhone acceptance without a user-device test.

**Licensing/provenance:** independent code using the publicly documented Apple plist format and Aidoku's `Backup.swift`, `BackupManga.swift`, `BackupLibraryManga.swift`, `BackupChapter.swift`, and `BackupHistory.swift` structures as format references. No Yomu source or binaries copied.
