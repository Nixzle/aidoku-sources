# Comix v132 update feed

This dedicated source list tests a clean-room iOS Cloudflare recovery path for
Comix. It keeps a bounded native request so Aidoku can present website
verification, then uses one persistent, same-origin WebView for signing and API
requests when the native transport remains blocked.

Add this URL in Aidoku Settings > Source Lists:

`https://nixzle.github.io/aidoku-sources/comix-v132/index.min.json`

Aidoku 0.9 or newer is required. Leave Request Mode on Automatic initially. If
the source still stalls, select WebView in Comix settings, run Verify Comix
Captcha, wait for it to complete, and retry Home. Back up Aidoku before testing
and do not delete the existing library. Website challenges and premium
permissions remain enforced.

The package compiled and loaded in the headless Aidoku runtime. That runtime has
no iOS WebView network trace, so acceptance remains pending on the affected
iPhone.
