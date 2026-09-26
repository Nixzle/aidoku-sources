# Nixzle's English Aidoku Sources

[![Daily source update](https://github.com/Nixzle/aidoku-sources/actions/workflows/daily-update.yml/badge.svg)](https://github.com/Nixzle/aidoku-sources/actions/workflows/daily-update.yml)

Public, unofficial English and multilingual source packages for Aidoku. The main list follows the active Aidoku community catalog so removed, unmaintained packages do not continue to appear healthy.

## Add to Aidoku

Paste this URL into Aidoku under Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/index.min.json`

The normal list contains the currently maintained packages that are not known to be broken. Comix and Read Comics Online require Aidoku 0.9 or newer. Aidoku 0.9 includes the current Cloudflare handling fixes needed by challenge-gated external sources. The source-list host is static GitHub Pages and normally responds in well under a second; browsing speed after installation depends on each source website.

### Reliability

The catalog is checked every day. Downloads are retried, packages are validated before publication, and the previous working package is retained when an individual upstream download fails. Critical sources also receive chapter-level endpoint smoke checks, and the public GitHub Pages feed is re-fetched after publication so a green updater cannot hide a broken deployed catalog. Repeated DNS or connection failures can temporarily quarantine a source; Cloudflare responses such as 403 or 429 count as reachable so protected sites are not hidden by mistake.

Known parser or website failures are quarantined manually until an upstream fix is available. Package provenance and SHA-256 checksums are recorded in each catalog's `inventory.json` and `CHECKSUMS.sha256`.

Current degraded and quarantined sources are listed in the [public status report](status.md), with a [machine-readable JSON version](https://nixzle.github.io/aidoku-sources/status.json). Its timestamp changes only when catalog or health status changes, although checks still run daily.

### ReadComicOnline replacement

The original ReadComicOnline websites no longer resolve, so that broken entry is hidden from the maintained list. Install **Read Comics Online** (with spaces) instead. It is a separate website, so bookmarks from the original source do not migrate automatically.

Read Comics Online v4 uses the current community reader code, with a client-visible
package revision. Complete any Cloudflare challenge shown **inside Aidoku** and retry.
The current community package does not include the retired custom “Verify Read Comics
Online Access” setting. Use Aidoku 0.9 or newer; a repository update does not update
the application itself. If a challenge repeats, record the source and app versions
and test the same chapter with the reader's website button before clearing caches.


Comix already reuses its verification cookie, but Comix itself currently gives that cookie a short lifetime (about 30 minutes). Use **Source Settings > Verify Comix Captcha** when it expires. That limit is controlled by Comix and cannot be extended by this catalog host. **BatCave** is included as a second comics fallback; open its source settings and use **Verify BatCave Access** if it fails to load.

Older packages that are no longer present in the maintained catalog are preserved in a separate legacy list. It is an archive, not a recommended list, and many entries no longer work because their websites or parsers changed:

`https://nixzle.github.io/aidoku-sources/legacy/index.min.json`

Do not add the legacy list unless you specifically need an old source. It no longer duplicates sources already available from the maintained list.

Packages marked for personal download only by their maintainer are intentionally excluded from this public repository. External sources are unofficial and are not affiliated with Aidoku or the websites they access.

### Updating an existing installation

Refresh this source list and install the Read Comics Online **v4 or newer** source
update in Aidoku's Browse tab. This is a source-package version, not the Aidoku app
version. Aidoku 0.9 or newer remains the supported application floor for this source.
The update keeps `en.readcomicsonline`, its website and chapter keys unchanged;
do not remove your library or uninstall Aidoku to obtain it.

The former corrected v3 package was not discoverable as an update by clients that
already had a different v3 installed. This list now publishes explicit, monotonic
client revisions for that source. Only its manifest version changes; upstream WASM,
settings and other payload bytes are preserved and identified in `inventory.json`.

A **blocked** functional result is not a successful reader test. See the functional
workflow's per-source summary and its open reliability incident, not just the job
badge. A screenshot containing only a chapter number cannot identify the affected
source. For chapter failures include source name/version, series title, chapter,
Aidoku version and whether the reader's website button loads that same chapter.
Never post account cookies or access tokens.
