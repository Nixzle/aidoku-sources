# Comix and Asura reader repair candidates

Based on MIT OR Apache-2.0 Aidoku-Community/sources. Comix v131 is synchronized to upstream commit 0b512d60d5337de5baf7bb4f2ee85afe111e7203. Original license files are retained here. No Yomu packages/code are included.

Comix v131: the maintained upstream v23 implementation with only the package version and Aidoku 0.9 application floor changed. It uses Aidoku's repaired native Cloudflare request path and the upstream hidden WebView only for Comix's signer and response decoder. The previous custom transport layer was removed after it failed real-device acceptance.

Asura v20: native-first bounded WebView recovery for search, details, chapter API and reader HTML; robust page formats with explicit errors instead of empty/partial chapters; preserve subscription gates; add image Referer and separate access-verification control.

No challenge is solved automatically and no paid chapter restriction is bypassed. Verification cookies remain inside Aidoku's source settings and request handling.

Builds use checked-in Cargo.lock files. The new workflow builds and packages a separate candidate feed, runs transport/parser tests, and runs the actual source WASM. Headless WebViews are not WKWebView and cannot validate cookies/CAPTCHA or iOS rendering. Promotion to the maintained source list requires a device reader check. Source IDs are unchanged; do not delete your library.
