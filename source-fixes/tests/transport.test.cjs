const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('source-fixes/shared/fetch.js', 'utf8');
function environment(implementation) {
    const calls = [];
    const context = {URL, TextDecoder, AbortController, setTimeout, clearTimeout,
        location: {origin:'https://comix.to'},
        fetch: async (...args) => { calls.push(args); return implementation(...args); }};
    return {fn:vm.runInNewContext('('+source+')',context), calls};
}
function response(text, status=200, headers={}) {
    let read = false;
    return {status, headers:{get:key => headers[key] ?? null},
        body:{getReader:() => ({read:async() => read ? {done:true} : (read=true,{done:false,value:Buffer.from(text)}), cancel:async()=>{}})}};
}
test('same-origin GET keeps browser cookies and blocks redirects',async()=>{
    const e=environment(()=>response('{"result":1}'));
    const result=JSON.parse(await e.fn('https://comix.to/api/v1/test',{}));
    assert.equal(result.status,200);assert.equal(result.body,'{"result":1}');
    assert.equal(e.calls[0][1].credentials,'include');assert.equal(e.calls[0][1].redirect,'error');
    assert.equal(e.calls[0][1].method,'GET');
});
test('rejects cross-origin, HTTP and embedded credentials without a request',async()=>{
    const e=environment(()=>response(''));
    for(const url of ['https://evil.example/x','https://comix.to.evil.example/x','http://comix.to/x','https://user:password@comix.to/x','https://comix.to:8443/x']) await assert.rejects(e.fn(url,{}));
    assert.equal(e.calls.length,0);
});
test('protection is explicit and never turned into chapter content',async()=>{
    const e=environment(()=>response('challenge',403,{'cf-mitigated':'challenge'}));
    const result=JSON.parse(await e.fn('https://comix.to/',{}));
    assert.equal(result.status,403);assert.equal(result.challenge,true);
});
test('retains encrypted response marker for Comix decoder',async()=>{
    const e=environment(()=>response('encoded',200,{'x-enc':'1'}));
    assert.equal(JSON.parse(await e.fn('https://comix.to/api/v1/test',{})).x_enc,'1');
});
test('bounds declared and streamed response sizes',async()=>{
    let e=environment(()=>response('',200,{'content-length':String(9*1024*1024)}));
    await assert.rejects(e.fn('https://comix.to/',{}),/too large/);
    e=environment(()=>response('x'.repeat(8*1024*1024+1)));
    await assert.rejects(e.fn('https://comix.to/',{}),/too large/);
});
test('network rejection is not silently accepted',async()=>{
    const e=environment(()=>{throw new Error('network unavailable')});
    await assert.rejects(e.fn('https://comix.to/',{}),/network unavailable/);
});
