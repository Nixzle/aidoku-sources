//! Page representation normalization shared by the API and Astro reader.
use aidoku::alloc::{String, Vec, string::ToString};
use serde_json::Value;

fn untag(value: &Value) -> &Value {
    if let Some(items) = value.as_array()
        && items.len() == 2 && matches!(items[0].as_u64(), Some(0 | 1)) {
        &items[1]
    } else { value }
}

pub fn urls(value: &Value) -> core::result::Result<Vec<String>, String> {
    let items = untag(value).as_array().ok_or("Chapter has no page array")?;
    if items.is_empty() { return Err("Chapter has no pages; it may require login or be unavailable".into()); }
    let mut result = Vec::with_capacity(items.len());
    for item in items {
        let item = untag(item);
        let value = if let Some(object) = item.as_object() {
            untag(object.get("url").ok_or("Page URL is missing")?)
        } else { item };
        let url = value.as_str().ok_or("Page URL is not text")?.trim();
        if !url.starts_with("https://") || url.len() > 8192 || url.chars().any(|c| c.is_control() || c.is_whitespace()) {
            return Err("Unsafe or unsupported chapter image URL".into());
        }
        result.push(url.to_string());
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn plain_api_and_astro_pages_keep_order() {
        let expected = ["https://cdn.example/1.webp", "https://cdn.example/2.webp"];
        assert_eq!(urls(&json!(expected)).unwrap(), expected);
        assert_eq!(urls(&json!([{"url":expected[0]}, {"url":expected[1]}])).unwrap(), expected);
        assert_eq!(urls(&json!([1, [[0,{"url":[0,expected[0]]}], [0,{"url":[0,expected[1]]}]]])).unwrap(), expected);
    }
    #[test]
    fn missing_or_invalid_pages_are_not_silent_success() {
        for value in [json!([]), json!(null), json!([{"url":null}]), json!(["https://cdn.example/1", {}]), json!(["javascript:alert(1)"])] {
            assert!(urls(&value).is_err(), "{value}");
        }
    }
}
