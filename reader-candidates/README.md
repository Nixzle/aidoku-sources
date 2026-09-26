# Reader repair candidates

## Comix v24 retired

The local Comix v24 candidate is **not accepted for iPhone use**. Owner-device testing still produced Aidoku's offline/source failure. Do not treat its successful compile or headless fixtures as reader acceptance.

Current evidence shows two independent conditions:

- Comix keeps `https://comix.to` as its primary site and officially advertises `https://comix.ws` when the primary is unreachable.
- Some Aidoku devices can pass Cloudflare in WebKit while ordinary app networking remains rejected. The v24 candidate does not provide sufficient host/transport recovery for that device state.

The maintained external Yomu Comix package currently advertises the same source id (`en.comix`) at v126 and provides selectable connection handling. Its source list is maintained by its own author and is **not rehosted or repackaged here**:

`https://smexhy.github.io/yomu-aidoku-sources/comix/index.min.json`

This repository does not claim that external package as its own work. The old v24 artifact is retained only as historical evidence and must not be promoted into the normal Nixzle catalog.

## Asura Scans v20

Asura Scans v20 remains the qualified repair candidate. CI compiled the exact package WASM and the recorded functional test completed search, metadata/chapters, a 22-page page list and first-image retrieval.

## Recovery

Back up Aidoku before source changes. Source IDs are unchanged, but removing a source list does not automatically downgrade an already-installed higher source version. Do not delete the library merely to change source implementations.
