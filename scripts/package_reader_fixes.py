#!/usr/bin/env python3
"""Build installable candidate AIX packages; never modify the maintained feed."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
from update_sources import read_package
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'reader-candidates'
SOURCES={'en.comix':'comix','en.asurascans':'asurascans'}
def main():
    OUTPUT.mkdir(exist_ok=True)
    previous_inventory_path=OUTPUT/'inventory.json'
    previous_inventory={}
    if previous_inventory_path.is_file():
        previous_inventory={item['id']:item for item in json.loads(previous_inventory_path.read_text()).get('sources',[])}
    entries=[]; inventory=[]
    for source_id,crate in SOURCES.items():
        source=ROOT/'source-fixes'/source_id
        info=json.loads((source/'res/source.json').read_text())['info']
        wasm=source/'target/wasm32-unknown-unknown/release'/f'{crate}.wasm'
        assert wasm.is_file(),f'Missing compiled WASM: {wasm}'
        package_path=f'sources/{source_id}-v{info["version"]}.aix'
        target=OUTPUT/package_path;target.parent.mkdir(exist_ok=True)
        keep_existing=False
        if target.is_file():
            try:
                existing,_=read_package(target.read_bytes(),source_id,expected_id=source_id,expected_version=info['version'])
                keep_existing=existing['version']==info['version']
            except Exception:
                keep_existing=False
        if not keep_existing:
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
                for item in sorted((source/'res').glob('*')):
                    if item.is_file():archive.write(item,'Payload/'+item.name)
                archive.write(wasm,'Payload/main.wasm')
        data=target.read_bytes()
        _,icon=read_package(data,source_id,expected_id=source_id,expected_version=info['version'])
        with zipfile.ZipFile(target) as archive:
            packaged_wasm=archive.read('Payload/main.wasm')
        source_commit=(
            previous_inventory[source_id].get('sourceCommit')
            if keep_existing
            and source_id in previous_inventory
            and previous_inventory[source_id].get('version') == info['version']
            else os.environ.get('GITHUB_SHA')
        )
        provenance=(
            f'https://github.com/Nixzle/aidoku-sources/tree/{source_commit}/source-fixes/{source_id}'
            if source_commit
            else 'https://github.com/Nixzle/aidoku-sources/tree/main/source-fixes'
        )
        icon_path=f'icons/{source_id}-v{info["version"]}.png'
        (OUTPUT/'icons').mkdir(exist_ok=True);(OUTPUT/icon_path).write_bytes(icon)
        entries.append({'id':source_id,'name':info['name'],'version':info['version'],
            'downloadURL':package_path,'iconURL':icon_path,'languages':info['languages'],
            'baseURL':info['url'],'contentRating':info['contentRating'],'minAppVersion':info['minAppVersion']})
        inventory.append({'id':source_id,'version':info['version'],'file':package_path,
            'sha256':hashlib.sha256(data).hexdigest(),'wasmSha256':hashlib.sha256(packaged_wasm).hexdigest(),
            'provenanceURL':provenance,
            'sourceCommit':source_commit,
            'acceptance':'Candidate: requires iOS reader verification'})
    entries.sort(key=lambda x:x['id']);inventory.sort(key=lambda x:x['id'])
    feed={'name':'Nixzle Reader Repair Candidates (iOS verification pending)','sources':entries}
    (OUTPUT/'index.json').write_text(json.dumps(feed,indent=2)+'\n')
    (OUTPUT/'index.min.json').write_text(json.dumps(feed,separators=(',',':'))+'\n')
    (OUTPUT/'inventory.json').write_text(json.dumps({'sourceCount':len(inventory),'sources':inventory},indent=2)+'\n')
    (OUTPUT/'CHECKSUMS.sha256').write_text(''.join(x['sha256']+'  '+x['file']+'\n' for x in inventory))
    print(json.dumps(inventory,indent=2))
if __name__=='__main__':main()
