const cp=require("node:child_process"),fs=require("node:fs"),http=require("node:http"),os=require("node:os"),path=require("node:path"),assert=require("node:assert/strict");
const root=path.resolve(__dirname,".."),chromePath="C:/Program Files/Google/Chrome/Application/chrome.exe";
const mime={".html":"text/html",".mjs":"text/javascript",".js":"text/javascript",".css":"text/css",".svg":"image/svg+xml",".webmanifest":"application/manifest+json",".aib":"application/octet-stream",".cbz":"application/zip"};
const sleep=t=>new Promise(r=>setTimeout(r,t));
async function run(){
  assert.ok(fs.existsSync(chromePath),"Chrome missing");
  let browser,server,socket;const profile=fs.mkdtempSync(path.join(os.tmpdir(),"sanctum-reader-smoke-"));
  try{
    server=http.createServer((req,res)=>{let name;
      try{name=decodeURIComponent(new URL(req.url,"http://localhost").pathname)}catch{res.writeHead(400).end();return}
      let file=path.resolve(root,"."+name);
      if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return}
      if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,"index.html");
      if(!fs.existsSync(file)){res.writeHead(404).end();return}
      res.setHeader("Content-Type",mime[path.extname(file)]||"application/octet-stream");fs.createReadStream(file).pipe(res);
    });
    await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
    const base=process.env.SANCTUM_READER_TEST_URL || "http://127.0.0.1:"+server.address().port;
    browser=cp.spawn(chromePath,["--headless=new","--no-first-run","--disable-gpu","--disable-extensions","--no-default-browser-check","--remote-debugging-port=0","--remote-allow-origins=*","--user-data-dir="+profile,base+"/reader/"],{windowsHide:true,stdio:"ignore"});
    const debug=path.join(profile,"DevToolsActivePort");
    for(let i=0;i<90&&!fs.existsSync(debug);i++)await sleep(120);
    assert.ok(fs.existsSync(debug),"Chrome remote debugger failed to start");
    const port=fs.readFileSync(debug,"utf8").split(/\r?\n/)[0];
    let tabs=[];
    for(let i=0;i<35;i++){try{tabs=await(await fetch("http://127.0.0.1:"+port+"/json/list")).json()}catch{}
      if(tabs.some(x=>x.type==="page"&&x.url.includes("/reader/")))break;
      await sleep(100);}
    const tab=tabs.find(x=>x.type==="page"&&x.url.includes("/reader/"));
    assert.ok(tab,"No reader page");
    socket=new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true})});
    const pending=new Map();let seq=0;
    socket.addEventListener("message",e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}});
    const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))});
    const evalJs=async expression=>{const r=await send("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
    const until=async(expression,expected,label)=>{for(let i=0;i<50;i++){if(await evalJs(expression)===expected)return;await sleep(130)}throw Error("Timed out: "+label)};
    await send("Runtime.enable");
    await until('document.documentElement.dataset.sanctumReady',"true","App modules ready");
    await until('document.querySelector("#statTotal")?.textContent',"0","App boot");
    const importAib='(async()=>{const r=await fetch("./test-fixtures/sample.aib");const dt=new DataTransfer();dt.items.add(new File([await r.arrayBuffer()],"sample.aib"));const el=document.getElementById("aidokuFile");el.files=dt.files;el.dispatchEvent(new Event("change",{bubbles:true}));return true})()';
    assert.equal(await evalJs(importAib),true);
    await until('document.querySelector("#statTotal")?.textContent',"2","Aidoku import");
    assert.equal(await evalJs('document.querySelector("#library").textContent.includes("Second Half")'),true);
    const importCbz='(async()=>{const r=await fetch("./test-fixtures/sample.cbz");const dt=new DataTransfer();dt.items.add(new File([await r.arrayBuffer()],"sample.cbz"));const el=document.getElementById("cbzFile");el.files=dt.files;el.dispatchEvent(new Event("change",{bubbles:true}));return true})()';
    assert.equal(await evalJs(importCbz),true);
    await until('document.querySelector("#cbzCounter")?.textContent',"Page 1 / 2","CBZ first page");
    await evalJs('document.querySelector("#cbzNext").click()');
    await until('document.querySelector("#cbzCounter")?.textContent',"Page 2 / 2","CBZ second page");
    await evalJs('document.querySelector("#cbzClose").click()');
    await until('document.querySelector("#statTotal")?.textContent',"3","Local file catalogue");
    const data='new Promise(resolve=>{const o=indexedDB.open("sanctum-reader-library",1);o.onsuccess=()=>{const t=o.result.transaction("state","readonly"),q=t.objectStore("state").get("library");q.onsuccess=()=>resolve(q.result.map(x=>({title:x.title,sourceId:x.sourceId,page:x.page})))}})';
    const persisted=await evalJs(data);
    assert.equal(persisted.length,3);
    assert.equal(persisted.find(x=>x.sourceId==="local-file").page,2);
    await send("Page.enable");await send("Page.reload",{ignoreCache:true});
    await until('document.querySelector("#statTotal")?.textContent',"3","Reload persistence");
    console.log(JSON.stringify({result:"PASS",browser:"Chrome headless",aidokuTitles:2,cbzPages:2,storedTitles:3}));
  }finally{try{socket?.close()}catch{}try{browser?.kill()}catch{}try{server?.close()}catch{}await sleep(250);try{fs.rmSync(profile,{recursive:true,force:true,maxRetries:5,retryDelay:250})}catch{}}
}
run().catch(e=>{console.error("READER_BROWSER_SMOKE_FAILED",e.stack||e);process.exitCode=1});
