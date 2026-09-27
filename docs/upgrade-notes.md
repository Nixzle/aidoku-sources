# Reliability upgrade — September 2026

- An upstream version equal to a local override no longer stops unrelated updates.
  Identical packages are accepted; differing bytes keep the pinned local package
  and emit a workflow warning. A strictly newer upstream package retires the override.
- Override packages receive a live upstream check rather than being mistaken for
  an upstream cache hit. A network failure can still use the verified local cache.
- The ReadComicsOnline v3 archive has an explicit SHA-256 and an immutable commit
  link. This records artifact provenance, not a reproducible-build attestation.
- Daily failures open/update one bot-owned GitHub issue; a successful run closes
  it. User-created issues are not modified. Repository notification preferences
  determine whether GitHub sends email. This does not detect a disabled schedule.
- Changes to updater code/policy trigger a refresh on main in addition to the daily
  schedule. Generated catalog commits do not recursively trigger it.
- The install page queries public GitHub run status on load, separately from the
  catalog's content-change timestamp. API limits/errors are shown as unavailable,
  never as healthy. A successful run older than 48 hours is marked overdue.
- PoppingMango's experimental Paperback ports are linked to their original install
  page, not mirrored, in keeping with the author's redistribution request.

## Comix follow-up

Comix v24 was added later as a reproducible rebuild of the official community
source with Aidoku 0.9 as its minimum app version. Aidoku 0.9 contains the app-
level Cloudflare repair; hosting the catalog on GitHub still cannot remove
Comix's own human-verification checks. Package validation and HTTP reachability
do not by themselves prove home, search, chapter parsing, or image loading on
an iPhone, so the installed v24 build still needs device acceptance.

Yomu's packages must not be repackaged here. Any independent transport implementation needs
independent code, supported Aidoku APIs, bounded retries, persistent-session
testing, and a new version to avoid replacing already-published package bytes.

Build attestations require a committed and reproducible source/toolchain build;
the current archive checksum is not a substitute for that work.
