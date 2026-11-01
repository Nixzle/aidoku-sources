# Comix v140 repair feed

This feed distributes Nixzle's repaired Comix source under the existing
`en.comix` identity. The URL is unchanged so existing testers can update in place.

Add this URL in Aidoku Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/comix-v132/index.min.json`

**Owner-device result: FAILED. Do not install or update to v140 expecting reliable chapter reading.** Aidoku 0.9 or newer is required for this historical candidate.

See [device recovery](../docs/COMIX_DEVICE_RECOVERY.md) for an original-publisher replacement that preserves the source identity.
Use the current Aidoku build, leave Request Mode on Automatic initially, then
run Verify Comix Captcha in the source settings and complete the website check.
Back up Aidoku before testing and keep the existing library.

## What v140 repairs

- Current full image URLs work without `baseUrl`; signed image URLs retain
  their exact value. Legacy shared-base responses remain supported.
- Verification treats `waf_pass` as opaque and checks actual signed API access.
  Neither a guessed timestamp nor a fixed thirty-minute lifetime implies success.
- Secure-module discovery checks multiple existing or new eligible objects,
  including nonenumerable properties. It requires both signing and decoding
  callbacks from one installer invocation and has explicit discovery limits.
- Successive API requests wait one second before signing. Native-to-browser
  recovery gets its own interval, and re-verification preserves pacing.
- Interrupted lists resume from a recent bounded checkpoint after live first-page validation; reset through Source Settings > Chapter List Recovery.
- Packaging updates only Comix and retains the other candidates and their
  original checksums and provenance.

The package is built from this repository's licensed source, with its exact
source revision and package/WASM checksums recorded in `inventory.json`.
The normal catalog remains quarantined until the affected iPhone can verify,
open a chapter and render its pages. Automated checks do not certify iOS WebView
cookie persistence or website challenge acceptance. Website challenges and
premium permissions remain enforced.

## Build evidence

[Build 41276553700](https://github.com/Nixzle/aidoku-sources/actions/runs/41276553700)
compiled Comix v140 from commit `9f685b1da1a22fe7c85c16094fefa428547bc9eb`.
Its package SHA-256 is `6617baf124dca001e77896c3384a0e73afce4115cd522c4f93a62dcd1f781c97`.
The 117 Python and 17 JavaScript regressions passed, as did the Rust runtime
tests and catalog checks. Headless functional acceptance is still **inconclusive**
because it cannot reproduce iOS WebView conditions. A real iPhone chapter test
is required before removing source quarantine.
