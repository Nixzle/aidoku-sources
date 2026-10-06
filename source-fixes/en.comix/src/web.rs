// reference: https://github.com/nobottomline/extensions-source/blob/c8fe930f315f3baee23587559edfceab5e969202/src/en/comix/src/eu/kanade/tachiyomi/extension/en/comix/Signer.kt
use crate::{
	BASE_URL, COMIX_ORIGINS,
	helpers::create_request_get,
	models::ErrorResponse,
	transport::{self, ReaderRequest, ReaderResponse as Response},
};
use aidoku::{
	HashMap, Result,
	alloc::{string::String, string::ToString, vec::Vec},
	helpers::uri::QueryParameters,
	imports::js::WebView,
	prelude::*,
};
use regex::Regex;
use serde::{Deserialize, de::DeserializeOwned};
use serde_json::Value;

const MODULE_TOKEN: &str = "__AIDOKU_COMIX_MODULE__";

const GET_VMOBJ_JS: &str = "\
const vmKey = '__AIDOKU_COMIX_MODULE__';\
const vmObj = window[vmKey];\
if (!vmObj || typeof vmObj !== 'object' || vmObj === window) {\
	return '';\
}";

const INSTALLER_REQUEST_TOKEN: &str = "__AIDOKU_INSTALLER_REQUEST_TOKEN__";
const INSTALLER_RESPONSE_TOKEN: &str = "__AIDOKU_INSTALLER_RESPONSE_TOKEN__";

const SAFE_STUB: &str =
	"<!doctype html><html><head><meta charset=\"utf-8\"></head><body></body></html>";

const CF_CHALLENGE_ERROR_MESSAGE: &str = "Response returned CF challenge page instead of JSON data. If problem persist, please clear the source cache and restart the application to resolve this issue.";

const WAF_CHALLENGE_KEY: &str = "captcha_required";
const WAF_CHALLENGE_ERROR_MESSAGE: &str = "Response returned WAF challenge page instead of JSON data. Please open Comix Settings and Verify Captcha to resolve this issue.";

#[derive(Deserialize)]
struct AxiosRequest {
	url: String,
	params: Option<HashMap<String, Value>>,
}

pub struct ComixWebView {
	web_view: WebView,
	is_initialized: bool,
	prefer_browser: bool,
}

impl ComixWebView {
	pub fn new() -> Self {
		Self {
			web_view: WebView::new(),
			is_initialized: false,
			prefer_browser: false,
		}
	}

	pub fn reset(&mut self) {
		self.is_initialized = false;
		self.prefer_browser = false;
		self.web_view = WebView::new();
	}

	fn send_reader_request(&mut self, request: ReaderRequest) -> Result<Response> {
		let (response, used_browser) =
			request.send_with_view_observed(&self.web_view, self.prefer_browser)?;
		if used_browser {
			self.prefer_browser = true;
		}
		Ok(response)
	}

	fn load_webview(&mut self) -> Result<()> {
		self.reset();
		// Do not navigate the hidden view to the live SPA: ads and challenge
		// subresources can prevent the page-finished callback from returning.
		// A local document with the real origin gives fetch() the first-party
		// cookie jar without introducing an unbounded navigation.
		self.web_view.load_html_blocking(SAFE_STUB, Some(BASE_URL))?;

		let request = ReaderRequest::new(
			create_request_get(BASE_URL)?,
			BASE_URL,
			COMIX_ORIGINS,
			HashMap::new(),
		)?;
		// This native-first request still gives Aidoku an opportunity to present
		// its Cloudflare verification sheet. If WebKit succeeds instead, the
		// browser latch prevents the same failed native probe on every API call.
		let response = self.send_reader_request(request)?;
		self.find_secure_module_src(&response)?;
		self.find_functions()?;
		self.is_initialized = true;
		Ok(())
	}

	fn find_secure_module_src(&mut self, response: &Response) -> Result<()> {
		let main_module_src = response
			.get_html()?
			.select("head > script[type=\"module\"][src*=\"main\"]")
			.and_then(|e| e.first())
			.and_then(|e| e.attr("src"))
			.ok_or(error!("Main module not found"))?;
		let main_module_url = if main_module_src.starts_with("https://") {
			main_module_src.to_string()
		} else {
			format!("{BASE_URL}/{}", main_module_src.trim_start_matches('/'))
		};
		transport::origin_for(&main_module_url, COMIX_ORIGINS)?;
		let main_module_request = ReaderRequest::new(
			create_request_get(&main_module_url)?,
			&main_module_url,
			COMIX_ORIGINS,
			HashMap::new(),
		)?;
		let main_module_contents = self.send_reader_request(main_module_request)?.get_string()?;
		let secure_script_regex = Regex::new("(secure-[A-Za-z0-9_-]+?\\.js)")
			.map_err(|_| error!("Invalid Comix module pattern"))?;
		let secure_script_path = secure_script_regex
			.captures(&main_module_contents)
			.and_then(|captures| captures.get(1).map(|value| value.as_str()))
			.ok_or_else(|| error!("Secure module not found"))?;
		let module_directory = main_module_url
			.rsplit_once('/')
			.map(|(directory, _)| directory)
			.ok_or_else(|| error!("Invalid main module path"))?;
		let secure_module_url = format!("{module_directory}/{secure_script_path}");
		transport::origin_for(&secure_module_url, COMIX_ORIGINS)?;
		let secure_module_request = ReaderRequest::new(
			create_request_get(&secure_module_url)?,
			&secure_module_url,
			COMIX_ORIGINS,
			HashMap::new(),
		)?;
		let secure_module_source = self.send_reader_request(secure_module_request)?.get_string()?;
		let Some(module_body) = secure_module_source
			.rfind("export")
			.filter(|&index| {
				secure_module_source[index + "export".len()..]
					.trim_start()
					.starts_with('{')
			})
			.map(|index| &secure_module_source[..index])
		else {
			bail!("Secure module exports not found");
		};
		let module_token = serde_json::to_string(MODULE_TOKEN)?;
		let result = self.web_view.eval(&format!(
			"(() => {{
				const before = new Set(Object.keys(window));
				try {{
					{module_body}
					const candidates = Object.keys(window).filter((key) => {{
						if (before.has(key) || !key.startsWith('vm')) return false;
						const value = window[key];
						return value && typeof value === 'object' && value !== window &&
							Object.values(value).some((item) => typeof item === 'function');
					}});
					if (candidates.length !== 1) return 'error: secure module object not found';
					window[{module_token}] = window[candidates[0]];
					return 'ok';
				}} catch (e) {{
					return 'error: ' + e;
				}}
			}})()"
		))?;
		if result != "ok" {
			bail!("Failed to load secure module: {result}");
		}
		Ok(())
	}

	fn find_functions(&mut self) -> Result<()> {
		let result = self.web_view.eval(&format!(
			"(() => {{
			try {{
				{GET_VMOBJ_JS}
				let fnames = Object.keys(vmObj);
				let inst = '';
				for (let j = 0; j < fnames.length; j++) {{
					let fn = vmObj[fnames[j]];
					if (typeof fn !== 'function') continue;
					let ref = 'window[' + JSON.stringify(vmKey) + '].' + fnames[j];
					if (!inst) {{
						try {{
							let got = false;
							fn({{
								interceptors: {{
									request: {{ use: function() {{ got = true; }} }},
									response: {{ use: function() {{ got = true; }} }}
								}}
							}});
							if (got) {{
								inst = ref;
								fn({{
									interceptors: {{
										request: {{
											use: function (fn) {{ window['{INSTALLER_REQUEST_TOKEN}'] = fn; }},
										}},
										response: {{
											use: function (fn) {{ window['{INSTALLER_RESPONSE_TOKEN}'] = fn; }},
										}},
									}}
								}});
							}}
						}} catch (e) {{}}
					}}
				}}
				return inst;
			}} catch (e) {{}}
			return '';
		}})()",
		))?;
		if result.is_empty() {
			bail!("Failed to find installer function");
		}
		Ok(())
	}

	fn build_request(&mut self, url: &str) -> Result<ReaderRequest> {
		if !self.is_initialized {
			self.load_webview()?
		}

		transport::origin_for(url, COMIX_ORIGINS)?;
		let url_literal = serde_json::to_string(url)?;
		let result = transport::run_task(&self.web_view, &format!(
			"(async () => {{
			const url = new URL({url_literal});
			const result = Object.create(null);

			for (const [key, rawValue] of url.searchParams) {{
				const value = /^\\d+$/.test(rawValue)
					? Number(rawValue)
					: rawValue;

				const parts = key.replace(/\\]/g, '').split('[');
				if (parts.some(part => ['__proto__', 'constructor', 'prototype'].includes(part))) {{
					throw new Error('Unsafe query key');
				}}

				let current = result;

				for (let i = 0; i < parts.length; i++) {{
					const part = parts[i];
					const last = i === parts.length - 1;

					if (last) {{
						if (part === '') {{
							current.push(value);
						}} else if (current[part] === undefined) {{
							current[part] = value;
						}} else if (Array.isArray(current[part])) {{
							current[part].push(value);
						}} else {{
							current[part] = [current[part], value];
						}}
					}} else {{
						const nextPart = parts[i + 1];

						current[part] ??= nextPart === '' ? [] : {{}};
						current = current[part];
					}}
				}}
			}}

			const request = await window['{INSTALLER_REQUEST_TOKEN}']({{
				url: `${{url.origin}}${{url.pathname}}`,
				method: 'GET',
				params: result,
			}});

			return JSON.stringify(request);
		}})()"
		))?;

		let axios_request: AxiosRequest = serde_json::from_str(result.as_str())?;

		fn build_query(params_map: &HashMap<String, Value>) -> QueryParameters {
			let mut params = QueryParameters::new();

			for (key, value) in params_map {
				push_value(&mut params, key, value);
			}

			params
		}

		fn push_value(params: &mut QueryParameters, key: &str, value: &Value) {
			match value {
				Value::Null => {
					params.push_key(key);
				}

				Value::Bool(_) | Value::Number(_) | Value::String(_) => {
					let value_str = value.to_string();

					// Remove JSON string quotes
					let value_str = match value {
						Value::String(s) => s.as_str(),
						_ => value_str.as_str(),
					};

					params.push(key, Some(value_str));
				}

				Value::Array(arr) => {
					let array_key = format!("{key}[]");

					for item in arr {
						match item {
							Value::String(s) => {
								params.push(&array_key, Some(s));
							}
							_ => {
								let value_str = item.to_string();
								params.push(&array_key, Some(&value_str));
							}
						}
					}
				}

				Value::Object(obj) => {
					for (child_key, child_value) in obj {
						let nested_key = format!("{key}[{child_key}]");
						push_value(params, &nested_key, child_value);
					}
				}
			}
		}

		if let Some(params) = axios_request.params {
			let query = build_query(&params);
			let signed_url = format!("{}?{query}", axios_request.url);
			ReaderRequest::new(
				create_request_get(&signed_url)?,
				&signed_url,
				COMIX_ORIGINS,
				HashMap::new(),
			)
		} else {
			ReaderRequest::new(
				create_request_get(&axios_request.url)?,
				&axios_request.url,
				COMIX_ORIGINS,
				HashMap::new(),
			)
		}
	}

	pub fn send_request(&mut self, url: &str) -> Result<Response> {
		let request = self.build_request(url)?;
		self.send_reader_request(request)
	}

	pub fn decode_json_owned<T>(&mut self, response: &Response) -> Result<T>
	where
		T: DeserializeOwned,
	{
		if !self.is_initialized {
			self.load_webview()?;
		}

		let status_code = response.status_code();

		if status_code == 403
			&& response
				.get_header("cf-mitigated")
				.is_some_and(|value| value == "challenge")
		{
			bail!("{CF_CHALLENGE_ERROR_MESSAGE}")
		} else if status_code >= 400 {
			if response.status_code() == 403
				&& serde_json::from_slice::<ErrorResponse>(&response.get_data()?)
					.is_ok_and(|e| e.error == WAF_CHALLENGE_KEY)
			{
				bail!("{}", WAF_CHALLENGE_ERROR_MESSAGE)
			} else {
				bail!("Response Error: {}", response.status_code())
			}
		} else if let Some(enc) = response.get_header("x-enc") {
			let encoded_response = serde_json::to_string(&response.get_string()?)?;
			let enc_literal = serde_json::to_string(&enc)?;

			let result = transport::run_task(&self.web_view, &format!(
				"(async () => {{
					try {{
						let decoded = await window['{INSTALLER_RESPONSE_TOKEN}']({{
							data: JSON.parse({encoded_response}),
							status: 200,
							headers: {{
								'x-enc': {enc_literal},
							}},
						}});
						return JSON.stringify({{ result: decoded && decoded.data }});
					}} catch(e) {{
						return 'error: ' + e;
					}}
				}})()",
			))?;

			if result.starts_with("error:") {
				bail!("{result}");
			} else if result.is_empty() {
				bail!("Failed to fetch result")
			}

			serde_json::from_str(&result).map_err(|e| error!("Invalid json: {}", e))
		} else {
			let json_str = response.get_string()?;
			serde_json::from_str(&json_str).map_err(|e| error!("Invalid json: {}", e))
		}
	}

}
