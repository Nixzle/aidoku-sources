# Comix v134 update feed

This dedicated source list tests a clean-room iOS Cloudflare recovery path for
Comix. v134 follows Comix's 6 October secure-module contract, decodes every
response carrying `x-enc`, removes obsolete image descrambling and does not add
the Referer/Origin headers rejected by current image hosts. Automatic mode now
keeps using a successful WebView fallback instead of repeating a blocked native
request, and Home emits each healthy section without waiting for all four.

Add this URL in Aidoku Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/comix-v132/index.min.json`

Aidoku 0.9 or newer is required. Leave Request Mode on Automatic initially. If
the source still stalls, select WebView in Comix settings, run Verify Comix
Captcha, wait for it to complete, and retry Home. Back up Aidoku before testing
and do not delete the existing library. Website challenges and premium
permissions remain enforced.

The package compiled and loaded in the headless Aidoku runtime, and the same
signer/decoder algorithm returned live Comix results in an isolated browser.
That runtime still has no iOS WebView network trace, so acceptance remains
pending on the affected iPhone.
