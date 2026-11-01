# Comix v139 repair feed

This feed distributes Nixzle's repaired Comix source under the existing
`en.comix` identity. The URL is unchanged so existing testers can update in place.

Add this URL in Aidoku Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/comix-v132/index.min.json`

Refresh the list and update Comix to v139. Aidoku 0.9 or newer is required.
Use the current Aidoku build, leave Request Mode on Automatic initially, then
run Verify Comix Captcha in the source settings and complete the website check.
Back up Aidoku before testing and keep the existing library.

## What v139 repairs

- Current full image URLs work without `baseUrl`; signed image URLs retain
  their exact value. Legacy shared-base responses remain supported.
- Verification treats `waf_pass` as opaque and checks actual signed API access.
  Neither a guessed timestamp nor a fixed thirty-minute lifetime implies success.
- Secure-module discovery checks multiple existing or new eligible objects,
  including nonenumerable properties. It requires both signing and decoding
  callbacks from one installer invocation and has explicit discovery limits.
- Successive API requests wait one second before signing. Native-to-browser
  recovery gets its own interval, and re-verification preserves pacing.
- Packaging updates only Comix and retains the other candidates and their
  original checksums and provenance.

The package is built from this repository's licensed source, with its exact
source revision and package/WASM checksums recorded in `inventory.json`.
The normal catalog remains quarantined until the affected iPhone can verify,
open a chapter and render its pages. Automated checks do not certify iOS WebView
cookie persistence or website challenge acceptance. Website challenges and
premium permissions remain enforced.

## Build evidence

[Build 41091303157](https://github.com/Nixzle/aidoku-sources/actions/runs/41091303157)
compiled the source at `4fa7c8ca9a14aad56f8e87db7532e6fbfa6660cc` and passed
117 Python, 17 JavaScript and 16 Rust tests. The downloaded package resources
were checked against that exact commit, and package/WASM checksums matched the
build inventory. The headless functional result was **inconclusive**: the source
loaded, but search returned error -1 without a WebView network trace. No successful
iPhone chapter-rendering result is claimed.
