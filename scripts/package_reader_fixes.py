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
    entries=[]; inventory=[]
    for source_id,crate in SOURCES.items():
        source=ROOT/'source-fixes'/source_id
        info=json.loads((source/'res/source.json').read_text())['info']
        wasm=source/'target/wasm32-unknown-unknown/release'/f'{crate}.wasm'
        assert wasm.is_file(),f'Missing compiled WASM: {wasm}'
        package_path=f'sources/{source_id}-v{info["version"]}.aix'
        target=OUTPUT/package_path;target.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for item in sorted((source/'res').glob('*')):
                if item.is_file():archive.write(item,'Payload/'+item.name)
            archive.write(wasm,'Payload/main.wasm')
        data=target.read_bytes()
        _,icon=read_package(data,source_id,expected_id=source_id,expected_version=info['version'])
        icon_path=f'icons/{source_id}-v{info["version"]}.png'
        (OUTPUT/'icons').mkdir(exist_ok=True);(OUTPUT/icon_path).write_bytes(icon)
        entries.append({'id':source_id,'name':info['name'],'version':info['version'],
            'downloadURL':package_path,'iconURL':icon_path,'languages':info['languages'],
            'baseURL':info['url'],'contentRating':info['contentRating'],'minAppVersion':info['minAppVersion']})
        inventory.append({'id':source_id,'version':info['version'],'file':package_path,
            'sha256':hashlib.sha256(data).hexdigest(),'wasmSha256':hashlib.sha256(wasm.read_bytes()).hexdigest(),
            'provenanceURL':'https://github.com/Nixzle/aidoku-sources/tree/main/source-fixes',
            'sourceCommit':os.environ.get('GITHUB_SHA'), 'acceptance':'Candidate: requires iOS reader verification'})
    entries.sort(key=lambda x:x['id']);inventory.sort(key=lambda x:x['id'])
    feed={'name':'Nixzle Reader Repair Candidates (iOS verification pending)','sources':entries}
    (OUTPUT/'index.json').write_text(json.dumps(feed,indent=2)+'\n')
    (OUTPUT/'index.min.json').write_text(json.dumps(feed,separators=(',',':'))+'\n')
    (OUTPUT/'inventory.json').write_text(json.dumps({'sourceCount':len(inventory),'sources':inventory},indent=2)+'\n')
    (OUTPUT/'CHECKSUMS.sha256').write_text(''.join(x['sha256']+'  '+x['file']+'\n' for x in inventory))
    (OUTPUT/'README.md').write_text('Reader repair candidates. Source IDs are unchanged. Back up Aidoku before testing. Comix v24 and Asura v20 require Aidoku 0.9+. Website challenges and premium chapter permissions remain enforced. Compile/fixture tests are not an iPhone acceptance result.\n')
    print(json.dumps(inventory,indent=2))
if __name__=='__main__':main()
