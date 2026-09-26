//! Native-first, bounded WebView recovery. No CAPTCHA solving or credential export.
use aidoku::{HashMap, Result, alloc::{String, Vec, string::ToString},
    imports::{defaults::defaults_get, html::{Document, Html}, js::WebView,
              net::Request, std::sleep}, prelude::*};
use serde::Deserialize;

const FETCH_JS: &str = include_str!("fetch.js");
const MAX_TEXT: usize = 8 * 1024 * 1024;

#[derive(Deserialize)]
pub struct ReaderResponse {
    pub body: String,
    pub status: i32,
    pub url: String,
    pub x_enc: Option<String>,
    pub challenge: bool,
}
impl ReaderResponse {
    pub fn status_code(&self) -> i32 { self.status }
    pub fn get_header(&self, name: &str) -> Option<String> {
        if name.eq_ignore_ascii_case("x-enc") { self.x_enc.clone() }
        else if name.eq_ignore_ascii_case("cf-mitigated") && self.challenge { Some("challenge".into()) }
        else { None }
    }
    pub fn get_string(&self) -> Result<String> { Ok(self.body.clone()) }
    pub fn get_data(&self) -> Result<Vec<u8>> { Ok(self.body.as_bytes().to_vec()) }
    pub fn get_html(&self) -> Result<Document> { Ok(Html::parse_with_url(&self.body, &self.url)?) }
    pub fn json<T: serde::de::DeserializeOwned>(&self) -> Result<T> { Ok(serde_json::from_str(&self.body)?) }
    fn blocked(&self) -> bool {
        self.challenge || self.status == 403 || self.body.contains("\"captcha_required\"")
            || self.body.contains("<title>Security check</title>")
            || self.body.contains("<title>Just a moment...</title>")
    }
    fn checked(self) -> Result<Self> {
        if self.body.len() > MAX_TEXT { bail!("Source response exceeds the size limit"); }
        if self.blocked() { bail!("Website verification is required. Open this source's verification/login web page, complete its challenge, then retry. No chapter was returned."); }
        if self.status == 401 { bail!("This chapter requires a valid website login or subscription"); }
        if self.status == 429 { bail!("Website rate limit reached. Wait before retrying; repeated requests will not help"); }
        if !(200..300).contains(&self.status) { bail!("Website returned HTTP {}", self.status); }
        Ok(self)
    }
}

#[derive(Deserialize)]
struct Task { done: bool, result: Option<String>, error: Option<String> }

/// Poll a promise with a hard bound instead of relying on the reused-view async handler.
pub fn run_task(view: &WebView, expression: &str) -> Result<String> {
    view.eval(&format!(r#"(() => {{
        const state = {{done:false,result:null,error:null}};
        window.__aidokuReaderTask = state;
        Promise.resolve().then(() => ({expression})).then(value => {{
            if (typeof value !== 'string') throw new Error('Invalid browser response');
            state.result = value;
        }}).catch(() => {{ state.error = 'Browser request failed or was blocked; complete source verification and retry'; }})
        .finally(() => {{state.done = true;}});
        return '';
    }})()"#))?;
    for _ in 0..16 {
        let encoded = view.eval("JSON.stringify(window.__aidokuReaderTask)")?;
        let state: Task = serde_json::from_str(&encoded)?;
        if state.done {
            view.eval("delete window.__aidokuReaderTask; ''")?;
            if let Some(error) = state.error { bail!("{error}"); }
            return state.result.ok_or_else(|| error!("Browser returned no result"));
        }
        sleep(1);
    }
    let _ = view.eval("delete window.__aidokuReaderTask; ''");
    bail!("Browser request timed out. Complete source verification and retry");
}

pub fn origin_for<'a>(url: &str, allowed: &'a [&str]) -> Result<&'a str> {
    if url.chars().any(|c| c.is_control()) || url.contains('\\') { bail!("Unsafe source URL"); }
    allowed.iter().copied().find(|base| url == *base || url.strip_prefix(*base).is_some_and(|tail| tail.starts_with('/')))
        .ok_or_else(|| error!("Unexpected source host; request rejected"))
}

pub fn browser_get_in(view: &WebView, url: &str, allowed: &[&str], headers: &HashMap<String, String>) -> Result<ReaderResponse> {
    origin_for(url, allowed)?;
    let url_js = serde_json::to_string(url)?;
    // Cookies remain in the caller's persistent WebKit session. Never inject
    // Cookie/Host or send credentials across redirects.
    let mut safe_headers = HashMap::new();
    if let Some(value) = headers.get("Authorization") { safe_headers.insert("Authorization", value); }
    let header_js = serde_json::to_string(&safe_headers)?;
    let encoded = run_task(view, &format!("({FETCH_JS})({url_js}, {header_js})"))?;
    let response: ReaderResponse = serde_json::from_str(&encoded)?;
    origin_for(&response.url, allowed)?;
    response.checked()
}

pub fn browser_get(url: &str, allowed: &[&str], headers: &HashMap<String, String>) -> Result<ReaderResponse> {
    let origin = origin_for(url, allowed)?;
    let view = WebView::new();
    view.load_html_blocking("<!doctype html><html><head></head><body></body></html>", Some(origin))?;
    browser_get_in(&view, url, allowed, headers)
}

pub struct ReaderRequest {
    request: Request,
    url: String,
    allowed: &'static [&'static str],
    headers: HashMap<String, String>,
}
impl ReaderRequest {
    pub fn new(request: Request, url: &str, allowed: &'static [&'static str], headers: HashMap<String, String>) -> Result<Self> {
        origin_for(url, allowed)?;
        Ok(Self {request, url: url.into(), allowed, headers})
    }
    pub fn send_with_view(self, view: &WebView) -> Result<ReaderResponse> {
        let mode = defaults_get::<String>("connectionMode").unwrap_or_else(|| "auto".into());
        let legacy_fallback = defaults_get::<bool>("browserFallback").unwrap_or(true);
        let Self { request, url, allowed, headers } = self;
        if mode == "browser" {
            return browser_get_in(view, &url, allowed, &headers);
        }
        match request.send() {
            Ok(response) => {
                let value = ReaderResponse {status: response.status_code(),
                    body: response.get_string()?, url: url.clone(),
                    x_enc: response.get_header("x-enc"),
                    challenge: response.get_header("cf-mitigated").is_some_and(|h| h == "challenge")};
                if !value.blocked() && value.status < 500 { return value.checked(); }
                if mode == "native" { return value.checked(); }
            }
            Err(error) => {
                if mode == "native" || (mode == "auto" && !legacy_fallback) { return Err(error.into()); }
            }
        }
        if mode == "auto" && !legacy_fallback {
            bail!("Source request blocked; browser recovery is disabled in source settings");
        }
        browser_get_in(view, &url, allowed, &headers)
    }

    pub fn send(self) -> Result<ReaderResponse> {
        let mode = defaults_get::<String>("connectionMode").unwrap_or_else(|| "auto".into());
        let Self { request, url, allowed, headers } = self;
        if mode == "browser" {
            return browser_get(&url, allowed, &headers);
        }
        match request.send() {
            Ok(response) => {
                let value = ReaderResponse {status: response.status_code(),
                    body: response.get_string()?, url: url.clone(),
                    x_enc: response.get_header("x-enc"),
                    challenge: response.get_header("cf-mitigated").is_some_and(|h| h == "challenge")};
                if !value.blocked() && value.status < 500 { return value.checked(); }
                if mode == "native" { return value.checked(); }
            }
            Err(error) if mode == "native" => return Err(error.into()),
            Err(_) => {}
        }
        browser_get(&url, allowed, &headers)
    }

}

pub fn get(url: &str, allowed: &'static [&'static str], headers: HashMap<String, String>) -> Result<ReaderResponse> {
    let mut request = Request::get(url)?;
    for (key,value) in &headers { request.set_header(key,value); }
    ReaderRequest::new(request,url,allowed,headers)?.send()
}
