# Reader repair candidates

These are Comix v24 and Asura Scans v20 source packages for Aidoku 0.9 or newer, not an Aidoku app update. Back up Aidoku before testing. The maintained feed remains unchanged.

Add this separate list under Aidoku Settings > Source Lists, refresh it, then update the two sources:

`https://nixzle.github.io/aidoku-sources/reader-candidates/index.min.json`

Source IDs are unchanged. For Comix, use Source Settings > Verify Comix Captcha. Asura has a separate Verify Asura Access control; its account/subscription login is unchanged. No configuration here bypasses CAPTCHA or premium chapters.

## Verification

CI run 36220911474 compiled both exact package WASMs; 45 Python tests, 6 browser transport tests and 5 Rust tests passed. The Asura candidate returned 10 search results, 145 chapters, a 22-page chapter and a valid first image. Comix's headless check was blocked by HTTP 403, so the new WKWebView fallback still requires iPhone verification. Neither candidate is claimed iOS-verified. See verification.json and inventory.json for exact hashes and evidence scope.

## Recovery

Keep your Aidoku backup. Removing a source list alone does not undo an installed higher-version source package; retain the original source package before testing. Do not delete your library. The unmodified maintained feed remains at ../index.min.json.

Code adapted from Aidoku-Community/sources. Full MIT and Apache-2.0 notices are alongside this document; source provenance is in the inventory and ../source-fixes/PROVENANCE.json.
