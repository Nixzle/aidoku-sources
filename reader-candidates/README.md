# Reader repair candidates

This isolated feed preserves Aidoku source IDs and does not add quarantined
sources to the normal catalog.

## Comix v140

**Owner iPhone chapter-reading acceptance failed on 2 November 2026. This build is retained for diagnosis and should not be installed as a fix.** See [Comix device recovery](../docs/COMIX_DEVICE_RECOVERY.md).

Comix v140 keeps the earlier image-URL, verification, secure-module discovery,
and API pacing repairs. It additionally stores one recent, bounded chapter-list
checkpoint, validates the live first page before reusing it, and resumes
interrupted pagination. It includes an optional manual checkpoint reset.
Reading history and library entries remain untouched.

Add this test feed in Aidoku Settings > Source Lists:

https://nixzle.github.io/aidoku-sources/reader-candidates/index.min.json

For historic testing only, updating to v140 and verifying the site if prompted was intended to
test the previously failing chapter. Try Connection > WebView if Automatic
cannot complete a normal website request.

Build: https://github.com/Nixzle/aidoku-sources/actions/runs/41276553700
The compiled package and tests passed. Headless website smoke remained
inconclusive; no iPhone chapter-rendering acceptance is claimed.
Other candidates retain their existing package hashes.
No CAPTCHA, subscription, or third-party restrictions are bypassed.
