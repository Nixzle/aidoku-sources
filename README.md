# Nixzle's English Aidoku Sources

[![Daily source update](https://github.com/Nixzle/aidoku-sources/actions/workflows/daily-update.yml/badge.svg)](https://github.com/Nixzle/aidoku-sources/actions/workflows/daily-update.yml)

Public, unofficial English and multilingual source packages for Aidoku. The main list follows the active Aidoku community catalog so removed, unmaintained packages do not continue to appear healthy.

## Add to Aidoku

Paste this URL into Aidoku under Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/index.min.json`

The normal list contains the currently maintained packages that are not known to be broken. Comix and Read Comics Online use maintained builds and require Aidoku 0.9 or newer. The source-list host is static GitHub Pages and normally responds in well under a second; browsing speed after installation depends on each source website.

### Verification results

[Public feed and package acceptance](https://github.com/Nixzle/aidoku-sources/actions/workflows/public-acceptance.yml) checks the actual GitHub Pages bytes against an immutable repository commit, including both lists and every package/icon. Each successful run retains a checksummed recovery bundle for 30 days.

[Functional source checks](https://github.com/Nixzle/aidoku-sources/actions/workflows/functional-smoke.yml) execute the published WASM for Comix, MangaDistrict and Read Comics Online through search, details, chapter discovery, page parsing and first-page retrieval. This headless test does not share your iPhone's cookies or implement its WebView. Blocked, unsupported, incomplete and failed runs are not passes.

A green updater only means the catalog was generated successfully. A green public-feed check proves delivery, not reading. See [verification and recovery](docs/reliability.md) for exact acceptance and troubleshooting.

### Reliability

The catalog is checked every day. Downloads are retried, packages are validated before publication, and the previous working package is retained when an individual upstream download fails. Repeated conclusive failures can temporarily quarantine a source. Authentication, forbidden access, rate limits and explicit Cloudflare challenges are reported separately. Protection is not counted as a successful parser or recovery check.

Known parser or website failures are quarantined manually until an upstream fix is available. Package provenance and SHA-256 checksums are recorded in each catalog's `inventory.json` and `CHECKSUMS.sha256`.

Current degraded and quarantined sources are listed in the [public status report](status.md), with a [machine-readable JSON version](https://nixzle.github.io/aidoku-sources/status.json). It records the last actual health sweep, per-source probe times and separate state-change times. Inconclusive sweeps retain counters and expose their evidence instead of hiding a failed check.

### ReadComicOnline replacement

The original ReadComicOnline websites no longer resolve, so that broken entry is hidden from the maintained list. Install **Read Comics Online** (with spaces) instead. It is a separate website, so bookmarks from the original source do not migrate automatically.

The maintained Read Comics Online build reuses the Cloudflare clearance obtained through **Source Settings > Verify Read Comics Online Access**. Complete the check once and return to Browse; repeat it only when the website expires the clearance. If it remains stuck, update Aidoku to 0.9 or newer, clear the network cache under Aidoku's Advanced settings, and retry.

Comix already reuses its verification cookie, but Comix itself currently gives that cookie a short lifetime (about 30 minutes). Use **Source Settings > Verify Comix Captcha** when it expires. That limit is controlled by Comix and cannot be extended by this catalog host. **BatCave** is included as a second comics fallback; open its source settings and use **Verify BatCave Access** if it fails to load.

Older packages that are no longer present in the maintained catalog are preserved in a separate legacy list. It is an archive, not a recommended list, and many entries no longer work because their websites or parsers changed:

`https://nixzle.github.io/aidoku-sources/legacy/index.min.json`

Do not add the legacy list unless you specifically need an old source. It no longer duplicates sources already available from the maintained list.

Packages marked for personal download only by their maintainer are intentionally excluded from this public repository. External sources are unofficial and are not affiliated with Aidoku or the websites they access.

The daily workflow also retains its lightweight critical chapter-endpoint checks and committed rollback metadata. Those HTTP checks are distinct from the exact-WASM reader checks linked above.
