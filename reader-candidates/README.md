# Reader repair candidates

## Comix v132

Comix v132 is the current Nixzle iPhone repair candidate for Aidoku 0.9+. It preserves source id en.comix.

It adds:
- a local same-origin WebView bootstrap that does not wait on Comix's live SPA or ad subresources;
- a bounded native request so Aidoku can present Cloudflare verification, followed by WebView recovery when native traffic remains blocked;
- signed API requests, response decoding, and first-party cookies kept in one persistent WebView session;
- strict `https://comix.to` origin checks, redirect rejection, response size limits, and request timeouts;
- Connection: Automatic / WebView / Native. Automatic is the default.

Add this source list in Aidoku Settings > Source Lists:

https://nixzle.github.io/aidoku-sources/reader-candidates/index.min.json

Then update Comix to v132. Start with Automatic. If the owner-reported failure remains, choose Connection > WebView, complete Verify Comix Captcha, and retry Home.

### Evidence ceiling

The locked build and repository checks pass for v132, and the exact package loads in the headless Aidoku runtime. Real iPhone acceptance remains pending because the headless runtime exposes no iOS WebView network trace. That inconclusive result is neither a failure nor a pass.

Asura Scans v20 remains in this candidate list and has passed the recorded search -> chapters -> pages -> first-image chain.

Back up Aidoku before testing. Do not delete your library. CAPTCHA and premium permissions are not bypassed.
