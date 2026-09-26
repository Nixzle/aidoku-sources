# Comix and Asura reader repair candidates

Based on MIT OR Apache-2.0 Aidoku-Community/sources at 5964c70831435db2109c020fa7dafbffaf40b525. Original license files are retained here. No Yomu packages/code are included.

Comix v24: native-first bounded same-origin WebView fallback for homepage, signer assets and signed API responses; asynchronous signer/response support; bounded module/image waits; refresh signer state after verification; restrict waf_pass to Comix, not image CDNs.

Asura v20: native-first bounded WebView recovery for search, details, chapter API and reader HTML; robust page formats with explicit errors instead of empty/partial chapters; preserve subscription gates; add image Referer and separate access-verification control.

All URL/header JavaScript arguments are JSON encoded. Browser cookies stay on the device. Browser fetches reject redirects and other origins, cap response bytes and abort at 12 seconds. No challenge is solved automatically and no paid chapter restriction is bypassed.

Builds use checked-in Cargo.lock files. The new workflow builds and packages a separate candidate feed, runs transport/parser tests, and runs the actual source WASM. Headless WebViews are not WKWebView and cannot validate cookies/CAPTCHA or iOS rendering. Promotion to the maintained source list requires a device reader check. Source IDs are unchanged; do not delete your library.
