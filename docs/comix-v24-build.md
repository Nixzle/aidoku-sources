# Comix v24 build record

Comix v24 is a rebuild of the official community source at commit
`0b512d60d5337de5baf7bb4f2ee85afe111e7203`. The source code remains the
community implementation; the only patch bumps the source version from 23 to
24 and raises `minAppVersion` from 0.8.4 to 0.9.

Aidoku 0.9 is required because its September 2026 release repairs the
Cloudflare handling failure that could leave challenged sources unusable on
Aidoku 0.8.4. The version bump also prevents the replacement from silently
changing an already-published v23 package.

Build input patch: `patches/en.comix-v24.patch`

Build command from `sources/en.comix`:

```text
aidoku package
aidoku verify package.aix
```

Published package SHA-256:

```text
59e61fb230216ed9f81e0bfbd683a22cfae86a487089d135173ccec54dcc09da
```

The upstream source is dual-licensed under MIT or Apache-2.0.
