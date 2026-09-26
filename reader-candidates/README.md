# Reader repair candidates

## Comix v127

Comix v127 is the current Nixzle iPhone repair candidate for Aidoku 0.9+. It preserves source id en.comix.

It adds:
- Connection: Auto / Native only / WebView only. Use WebView only when Cloudflare accepts the browser session but Aidoku native requests report offline/source errors.
- bounded WebView recovery for blocked native requests and transient 5xx edge failures;
- automatic startup failover from comix.to to Comix's official comix.ws alternate;
- separate verification state/actions for each official domain;
- deep-link and image Referer support for both official domains.

Add this source list in Aidoku Settings > Source Lists:

https://nixzle.github.io/aidoku-sources/reader-candidates/index.min.json

Then update Comix to v127. Start with Connection > WebView only for the owner-reported failure and complete Verify Comix Captcha. If the primary site is unavailable and the fallback asks for verification, use Verify comix.ws Captcha.

### Evidence ceiling

Exact-head CI run 36223909289 compiled the locked v127 WASM and passed the repository, browser-transport and runtime tests. The headless reader could reach both official hosts but received HTTP 403 from both because it has no user-completed WebKit challenge; therefore Comix remains iPhone verification pending. A headless protection block is not a failed iPhone WebView path and is not a pass.

Asura Scans v20 remains in this candidate list and has passed the recorded search -> chapters -> pages -> first-image chain.

Back up Aidoku before testing. Do not delete your library. CAPTCHA and premium permissions are not bypassed.
