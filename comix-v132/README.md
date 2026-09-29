# Comix v133 update feed

This dedicated source list tests a clean-room iOS Cloudflare recovery path for
Comix. v133 binds the current obfuscated security module to a private exact key;
it no longer searches the page for the first `vm*` global, which could select
Comix's large internal `vme_*` runtime and leave Home on empty skeletons. It also
keeps the bounded native verification trigger and same-origin WebView recovery.

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
