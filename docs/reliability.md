# Feed reliability and acceptance

## Three separate claims

1. **Catalog validation:** metadata, versions, safe paths, package contents, licenses and checksums agree in the repository.
2. **Public distribution acceptance:** the exact deployed manifests, every maintained and legacy package, and their icons match an immutable repository snapshot. A second manifest read detects a deployment changing halfway through the test.
3. **Functional source acceptance:** the exact package WASM can search, return meaningful metadata and chapters, parse a nonempty page list, and retrieve first-page content in the headless runner.

None of these claims alone proves that every chapter renders on an iPhone. Cloudflare WebView challenges, device cookies, image processing and application-version differences remain distinct evidence. The public status page labels each check by its scope and does not infer current health when GitHub's API cannot be read.

## Execution

Existing `Daily source update` remains the only scheduled catalog updater. Its concurrent lightweight chapter endpoint checks, required-package Pages checks and committed rollback metadata are preserved alongside the deeper acceptance workflows. The two acceptance workflows run after the existing `pages build and deployment` workflow. Both support a manual dispatch for recovery. No extra ChatGPT schedule, local wake process, privileged repository token or service account is required.

`Public feed acceptance` checks both feeds and all source packages, not just a sample. It compares served manifests to `git show <full SHA>:<path>` rather than a working copy with potentially different line endings. Failed delivery has a separate bot-owned incident from updater failures. It does not silently change the install URL or switch users to legacy sources.

`Functional source smoke` uses a separate hosted runner. Rust dependencies are locked, the donor is commit-pinned, and build caching is distinct from website acceptance so a Cloudflare block does not force rebuilding the runtime daily. Blocked and incomplete checks fail acceptance and retain their per-source evidence. The site is not automatically quarantined solely because a headless runner was blocked.

## Health state version 2

The checker separates `ok`, `auth_required`, `forbidden`, explicit `cloudflare_protected`, `rate_limited`, `restricted`, `dns_failure`, `dns_inconclusive`, `timeout`, `connection_failure`, `tls_failure`, `http_error`, `server_error`, `redirect_blocked`, `unsafe_target` and `probe_error`.

HTTP 200 is a reachability observation, not a parser pass. A generic 403 is not automatically called Cloudflare. Only the explicit challenge header receives that classification. Protected responses neither accumulate ordinary dead-site failures nor prove that a quarantined source has recovered.

Sweep quality measures **conclusive observations / attempted observations**. Conclusive failures count as evidence; failed probe implementations remain in the denominator. Separate public control requests provide evidence against a runner-wide outage. If the sweep is inconclusive, counters are preserved and observations still appear in the report. Existing minimum catalog size and maximum removal-ratio safeguards remain in effect.

The state migrates from version 1 on the next eligible sweep. `lastHealthSweepDate` prevents repeated same-day observations even when every source is healthy. `lastProbeAt` records actual observations; `lastStateChangeAt` changes when a classification/state changes. Healthy observations also remain inspectable. Daily freshness may produce a daily status commit; that is intentional, not hidden behind a frozen date.

Three failure samples quarantine an ordinary source. Two consecutive successful checks release it. An intervening failure resets the recovery streak. Required sources stay installed but failures are reported with high severity. Required does not mean healthy.

## Package provenance

The Read Comics Online override preserves its reviewed bytes and SHA-256. Its provenance page, raw artifact download URL, package repository, full commit and package path are separate fields. `sourceCommit` and `sourcePath` identify the committed **package artifact**; they do not claim that the underlying Rust implementation is reproducibly built from that commit. The validator rejects HTML blob pages as downloads, partial pins and contradictions between URL, path and commit.

## Runtime donor and limits

The runtime is adapted from the MIT-licensed Aidoku test-runner API at:

- Repository: `Aidoku/aidoku-rs`
- Commit: `e1320b0a2e11afb59e4dee374883a2212d325699`
- Relevant APIs: `crates/test-runner/src/bin/aidoku-test-runner.rs`, `src/libs`, `src/imports`, and `crates/lib/src/macros/mod.rs`
- Upstream limitations: `crates/test-runner/README.md`

The harness calls published source exports directly. It does not run an empty set of `$aidoku-test$` exports and call that a success. The adapter supports the deployed `std.print` and `std.abort` import names using their corresponding donor implementations. It never substitutes success stubs for unsupported operations.

The network adapter allows only bounded read/search requests over HTTPS, validates and pins public DNS answers, validates redirects before following them, caps responses and request counts, and discards credentials on cross-host redirects. Source execution has a 150-second per-source process timeout. No account cookies are copied into CI. Images are checked by response status and file signature; this is byte retrieval, not an iOS rendering test. Unsupported page formats and missing runtime capabilities remain failures, not fabricated passes.

The code builds against the hosted runner's existing Rust toolchain and uses the existing fontconfig runtime through the documented `RUST_FONTCONFIG_DLOPEN=on` mode. It does not install tooling on the owner's computer.

## Reproduce locally with existing tools

```sh
python -m unittest discover -s tests -p 'test_*.py'
python scripts/validate_catalog.py
python scripts/verify_public.py --expected-commit <full-deployed-commit-sha>
# Requires an existing Rust toolchain and supported runtime system libraries:
RUST_FONTCONFIG_DLOPEN=on cargo test --locked --manifest-path runtime-smoke/Cargo.toml
RUST_FONTCONFIG_DLOPEN=on cargo build --locked --manifest-path runtime-smoke/Cargo.toml
python scripts/functional_smoke.py --runner runtime-smoke/target/debug/aidoku-catalog-smoke
```

## Recovery

Every successful public acceptance retains `public.json` and `public.known-good.zip` for 30 days. The receipt records the tested commit, package hashes and the recovery ZIP's SHA-256. The ZIP contains both catalogs and their validated package/icon bytes, not an unverified manifest pointing to deleted packages. Local acceptance can produce the same bundle before any deployment.

Do not automatically revert `main` or overwrite concurrent edits. Identify the last accepted commit and the failing change, verify the recovery bundle hash, then apply a reviewed revert or restore the catalog artifacts on a recovery branch. Preserve a complete archive of the currently failing distribution for diagnosis. After merging a recovery, require a fresh public acceptance result. Older known-good bundles remain separate from newer failed receipts; do not treat the latest workflow badge as the bundle's verification.

## Chapter failure reports

A useful report includes source ID/name, source version, Aidoku version, series title, chapter number and whether the same page loads using the reader's website button. No account cookies or login tokens should be posted. A chapter number alone cannot identify a source or justify a parser change.

## Concurrent-change reconciliation

The integration preserves the Aidoku 0.9 compatibility floor for Comix and Read Comics Online, the existing critical chapter fixtures and their tests, and the previous metadata snapshot. The version-1 health state from the concurrent deployment is retained without replaying same-day failure counters; version 2 takes over on the next eligible sweep. A metadata-only rollback snapshot is not a substitute for the separately verified complete package recovery bundle.
