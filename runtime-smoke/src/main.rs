//! Executes the exact published WASM using Aidoku's pinned test-runner library.
//! This is a headless functional check, not proof of iOS WebView/cookie parity.
use aidoku::{Chapter, FilterValue, Manga, PageContext};
use aidoku_test_runner::{imports, libs::{DefaultValue, HttpMethod, NetRequest, NetResponse, StoreItem, WasmEnv}};
use anyhow::{bail, ensure, Context, Result};
use reqwest::{header::HeaderMap, Method, Url};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value as Json};
use sha2::{Digest, Sha256};
use std::{io::Read, net::{IpAddr, ToSocketAddrs}, sync::{Mutex, atomic::{AtomicUsize, Ordering}}, time::Duration};
use wasmer::{Function, FunctionEnv, FunctionEnvMut, Instance, Module, Store, Value};

static REQUESTS: AtomicUsize = AtomicUsize::new(0);
static NETWORK: Mutex<Vec<Json>> = Mutex::new(Vec::new());
const MAX_RESPONSE: u64 = 16 * 1024 * 1024;

fn public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v) => {
            let [a,b,_,_] = v.octets();
            !(v.is_private() || v.is_loopback() || v.is_link_local() || v.is_documentation()
              || v.is_unspecified() || v.is_broadcast() || a == 0 || a >= 224
              || (a == 100 && (64..=127).contains(&b)) || (a == 198 && (b == 18 || b == 19)))
        }
        IpAddr::V6(v) => {
            let s = v.segments();
            v.to_ipv4_mapped().map(public_ip_v4).unwrap_or(
                !v.is_loopback() && !v.is_unspecified() && (s[0] & 0xe000) == 0x2000
                && !(s[0] == 0x2001 && s[1] == 0x0db8))
        }
    }
}
fn public_ip_v4(ip: std::net::Ipv4Addr) -> bool { public_ip(IpAddr::V4(ip)) }

fn request(url: &Url, method: Method, headers: HeaderMap, body: Option<Vec<u8>>) -> Result<NetResponse> {
    ensure!(REQUESTS.fetch_add(1, Ordering::SeqCst) < 40, "request budget exhausted");
    ensure!(body.as_ref().map_or(0, Vec::len) <= 1024 * 1024, "request body exceeds limit");
    let mut url = url.clone();
    let mut headers = headers;
    let mut method = method;
    let mut body = body;
    for _ in 0..6 {
        ensure!(url.scheme() == "https" && url.username().is_empty() && url.password().is_none()
                && url.port_or_known_default() == Some(443), "unsafe request URL");
        let host = url.host_str().context("missing host")?.to_string();
        let addresses: Vec<_> = (host.as_str(),443).to_socket_addrs()?.collect();
        ensure!(!addresses.is_empty() && addresses.iter().all(|a| public_ip(a.ip())), "non-public network target");
        // Pin the checked DNS answer. Redirects are validated before every new request.
        let client = reqwest::blocking::Client::builder().no_proxy()
            .redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(15))
            .resolve(&host, *addresses.iter().find(|a| a.is_ipv4()).unwrap_or(&addresses[0])).build()?;
        let mut builder = client.request(method.clone(), url.clone()).headers(headers.clone())
            .header("User-Agent", "Aidoku/1 CFNetwork/3826.500.131 Darwin/24.5.0");
        if let Some(data) = body.clone() { builder = builder.body(data); }
        let response = builder.send()?;
        let status = response.status();
        NETWORK.lock().unwrap().push(json!({"host":host,"status":status.as_u16()}));
        let response_headers = response.headers().clone();
        if status.is_redirection() {
            let location = response_headers.get("location").context("redirect without location")?.to_str()?;
            let next = url.join(location)?;
            if next.host_str() != url.host_str() { headers = HeaderMap::new(); }
            if status.as_u16() == 303 || ((status.as_u16() == 301 || status.as_u16() == 302) && method == Method::POST) {
                method = Method::GET; body = None;
            }
            url = next; continue;
        }
        ensure!(response.content_length().unwrap_or(0) <= MAX_RESPONSE, "response exceeds limit");
        let mut data = Vec::new();
        response.take(MAX_RESPONSE+1).read_to_end(&mut data)?;
        ensure!(data.len() as u64 <= MAX_RESPONSE, "response exceeds limit");
        return Ok(NetResponse {url,status,headers:response_headers,data});
    }
    bail!("redirect limit exceeded")
}

fn execute_request(request_data: &mut NetRequest) -> Result<()> {
    let method = match request_data.method {
        HttpMethod::Get => Method::GET, HttpMethod::Post => Method::POST, HttpMethod::Head => Method::HEAD,
        _ => bail!("unsupported mutation method in read-only smoke test"),
    };
    let url = request_data.url.as_ref().context("missing source request URL")?;
    request_data.response = Some(request(url, method, request_data.headers.clone(), request_data.body.clone())?);
    Ok(())
}
fn common_send(env: &mut FunctionEnvMut<WasmEnv>, rid: i32) -> i32 {
    let Some(request) = env.data_mut().store.get_mut(rid).and_then(|item| item.as_request()) else { return -1; };
    match execute_request(request) { Ok(()) => 0, Err(_) => -10 }
}
fn send(mut env: FunctionEnvMut<WasmEnv>, rid: i32) -> i32 { common_send(&mut env,rid) }
fn send_all(mut env: FunctionEnvMut<WasmEnv>, ptr: u32, len: u32) -> i32 {
    if len > 40 { return -10; }
    let Ok(ids) = env.data().read_values::<i32>(&env,ptr,len) else { return -1; };
    for id in ids { let result = common_send(&mut env,id); if result != 0 { return result; } }
    0
}

#[derive(Deserialize)]
struct SearchResult { entries: Vec<Manga>, #[allow(dead_code)] has_next_page: bool }
// Keep all wire variants, including the image-reference slot absent in no-import builds.
#[allow(dead_code)]
#[derive(Deserialize)]
enum PageContent { Url(String, Option<PageContext>), Text(String), Image(i32), Zip(String,String) }
#[allow(dead_code)]
#[derive(Deserialize)]
struct Page { content: PageContent, thumbnail: Option<String>, has_description: bool, description: Option<String> }

struct Runner { store: Store, env: FunctionEnv<WasmEnv>, instance: Instance }
impl Runner {
    fn new(file: &str, settings: &Json) -> Result<Self> {
        let mut store = Store::default();
        let module = Module::from_file(&store,file)?;
        let mut data = WasmEnv::new();
        if let Some(items) = settings.as_object() {
            for (key,value) in items {
                let value = match value {
                    Json::Bool(b) => DefaultValue::Bool(*b),
                    Json::String(s) => DefaultValue::String(s.clone()),
                    Json::Number(n) if n.is_i64() => DefaultValue::Int(n.as_i64().unwrap() as i32),
                    Json::Array(xs) => DefaultValue::StringArray(xs.iter().filter_map(|x| x.as_str().map(String::from)).collect()),
                    _ => continue,
                };
                data.defaults.set(key.clone(),value);
            }
        }
        let env = FunctionEnv::new(&mut store,data);
        let mut imports = imports::generate_imports(&mut store,&env);
        // Published 0.8.x sources use std.* for the same logging/abort ABI.
        for name in ["print", "abort"] {
            let implementation = imports.get_export("env",name).context("missing donor env implementation")?;
            imports.define("std",name,implementation);
        }
        imports.define("net","send",Function::new_typed_with_env(&mut store,&env,send));
        imports.define("net","send_all",Function::new_typed_with_env(&mut store,&env,send_all));
        let instance = Instance::new(&mut store,&module,&imports)?;
        env.as_mut(&mut store).memory = Some(instance.exports.get_memory("memory")?.clone());
        instance.exports.get_function("start")?.call(&mut store,&[])?;
        Ok(Self {store,env,instance})
    }
    fn encode<T: Serialize>(&mut self, value: &T) -> Result<i32> { Ok(self.env.as_mut(&mut self.store).store.store_encoded(value)?) }
    fn call<T: DeserializeOwned>(&mut self, name: &str, args: &[i32]) -> Result<T> {
        let args: Vec<_> = args.iter().map(|x| Value::I32(*x)).collect();
        let values = self.instance.exports.get_function(name)?.call(&mut self.store,&args)?;
        let ptr = values.first().and_then(Value::i32).context("missing result pointer")?;
        ensure!(ptr > 0, "source returned error {ptr} at {name}");
        let length = self.env.as_ref(&self.store).read_u32(&self.store,ptr as u32)?;
        ensure!((8..=8*1024*1024).contains(&length), "source error or invalid result at {name}");
        let data = self.env.as_ref(&self.store).read_bytes(&self.store,ptr as u32+8,length-8)?;
        self.instance.exports.get_function("free_result")?.call(&mut self.store,&[Value::I32(ptr)])?;
        postcard::from_bytes(&data).with_context(|| format!("unsupported result encoding at {name}"))
    }
}

fn smoke(file: &str, query: &str, settings: &Json, report: &mut Json) -> Result<()> {
    report["stage"] = json!("runtime_load");
    let mut runner = Runner::new(file,settings)?;
    report["runtimeLoaded"] = json!(true);
    report["stage"] = json!("search");
    let q = runner.env.as_mut(&mut runner.store).store.store(StoreItem::String(query.to_string()));
    let filters = runner.encode(&Vec::<FilterValue>::new())?;
    let results: SearchResult = runner.call("get_search_manga_list", &[q,1,filters])?;
    ensure!(!results.entries.is_empty(), "search returned no entries");
    report["searchCount"] = json!(results.entries.len());
    let first = &results.entries[0];
    ensure!(!first.key.is_empty() && !first.title.is_empty(), "search returned invalid metadata");
    report["stage"] = json!("metadata_and_chapters");
    let descriptor = runner.encode(first)?;
    let manga: Manga = runner.call("get_manga_update", &[descriptor,1,1])?;
    ensure!(!manga.key.is_empty() && !manga.title.is_empty(), "empty manga metadata");
    let chapters = manga.chapters.as_ref().context("chapter list missing")?;
    let chapter: &Chapter = chapters.iter().find(|c| !c.locked && !c.key.is_empty()).context("no unlocked chapter")?;
    report["chapterCount"] = json!(chapters.len());
    report["stage"] = json!("page_list");
    let manga_id = runner.encode(&manga)?;
    let chapter_id = runner.encode(chapter)?;
    let pages: Vec<Page> = runner.call("get_page_list", &[manga_id,chapter_id])?;
    ensure!(!pages.is_empty(), "chapter returned no pages");
    report["pageCount"] = json!(pages.len());
    report["stage"] = json!("first_page_content");
    match &pages[0].content {
        PageContent::Url(url,context) => {
            let response = if runner.instance.exports.get_function("get_image_request").is_ok() {
                let url_id = runner.encode(url)?;
                let context_id = match context { Some(c) => runner.encode(c)?, None => -1 };
                let rid: i32 = runner.call("get_image_request", &[url_id,context_id])?;
                let request = runner.env.as_mut(&mut runner.store).store.get_mut(rid)
                    .and_then(|r| r.as_request()).context("source returned no image request")?;
                execute_request(request)?;
                request.response.take().context("empty image response")?
            } else {
                request(&Url::parse(url)?,Method::GET,HeaderMap::new(),None)?
            };
            ensure!(response.status.is_success(), "first page HTTP {}",response.status);
            let d = &response.data;
            let image_magic = d.starts_with(b"\x89PNG\r\n\x1a\n") || d.starts_with(b"\xff\xd8\xff")
                || d.starts_with(b"GIF8") || (d.len()>12 && &d[0..4]==b"RIFF" && &d[8..12]==b"WEBP")
                || (d.len()>12 && &d[4..8]==b"ftyp" && (&d[8..12]==b"avif" || &d[8..12]==b"avis"));
            ensure!(image_magic && d.len()>64, "first page is not an image response");
            report["firstPageBytes"] = json!(d.len());
            report["firstPageSha256"] = json!(format!("{:x}",Sha256::digest(d)));
        }
        PageContent::Text(text) => { ensure!(!text.trim().is_empty(),"empty text page"); report["firstPageTextLength"]=json!(text.len()); }
        _ => bail!("headless runner does not support this page content variant"),
    }
    report["stage"] = json!("complete");
    Ok(())
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.len()!=5 { eprintln!("usage: aidoku-catalog-smoke WASM QUERY SETTINGS_JSON REPORT_JSON"); std::process::exit(2); }
    let mut report = json!({"status":"failed","scope":"Exact WASM search, metadata, chapters, page list and first page bytes. Not iOS rendering.","runnerCommit":"e1320b0a2e11afb59e4dee374883a2212d325699"});
    let result = (|| -> Result<()> { let settings = serde_json::from_slice(&std::fs::read(&args[3])?)?; smoke(&args[1],&args[2],&settings,&mut report) })();
    match &result { Ok(()) => report["status"]=json!("passed"), Err(e) => report["error"]=json!(format!("{e:#}")) }
    report["network"] = json!(*NETWORK.lock().unwrap());
    std::fs::write(&args[4],serde_json::to_vec_pretty(&report).unwrap()).expect("write report");
    println!("{}",report);
    std::process::exit(if result.is_ok(){0}else{1});
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_private_addresses() {
        for ip in ["127.0.0.1","10.1.2.3","192.168.0.1","169.254.169.254","100.64.0.1","::1","fc00::1","::ffff:127.0.0.1"] {
            assert!(!public_ip(ip.parse().unwrap()),"{ip}");
        }
        assert!(public_ip("1.1.1.1".parse().unwrap()));
    }
    #[test]
    fn empty_search_is_not_functional_success() {
        #[derive(Serialize)] struct Wire {entries: Vec<Manga>,has_next_page:bool}
        let bytes=postcard::to_allocvec(&Wire{entries:vec![],has_next_page:false}).unwrap();
        let result:SearchResult=postcard::from_bytes(&bytes).unwrap();
        assert!(result.entries.is_empty());
    }
}
