//! The page response contract shared by the source and the executable regression tests.
use aidoku::alloc::{format, String, Vec};
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComixPages {
    pub base_url: Option<String>,
    pub items: Vec<ComixPage>,
}

#[derive(Deserialize)]
pub struct ComixPage {
    pub url: String,
}

fn has_https_origin(url: &str) -> bool {
    let Some(rest) = url.strip_prefix("https://") else { return false; };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
    !authority.is_empty()
        && !authority.contains('@')
        && !url.contains('\\')
        && !url.chars().any(|ch| ch.is_control() || ch.is_whitespace())
}

impl ComixPages {
    pub fn into_urls(self) -> core::result::Result<Vec<String>, &'static str> {
        if self.items.is_empty() {
            return Err("Comix returned no page images");
        }
        let base = self.base_url.as_deref().unwrap_or_default().trim_end_matches('/');
        self.items.into_iter().map(|page| {
            let url = if page.url.starts_with("https://") {
                // Signed CDN URLs must remain byte-for-byte unchanged.
                page.url
            } else if page.url.starts_with("//") {
                format!("https:{}", page.url)
            } else {
                let path = page.url.split(['?', '#']).next().unwrap_or_default();
                if page.url.is_empty() || path.contains(':') || !has_https_origin(base) {
                    return Err("Comix returned an image without a valid HTTPS URL or base URL");
                }
                format!("{base}/{}", page.url.trim_start_matches('/'))
            };
            if !has_https_origin(&url) {
                return Err("Comix returned an invalid image URL");
            }
            Ok(url)
        }).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn urls(json: &str) -> core::result::Result<Vec<String>, &'static str> {
        serde_json::from_str::<ComixPages>(json).unwrap().into_urls()
    }

    #[test]
    fn current_full_signed_url_needs_no_base_and_is_preserved_exactly() {
        let page = "https://img.example.net/a/page.webp?token=a%2Fb%2Bc&expires=123";
        let json = format!(r#"{{"items":[{{"url":"{page}"}}]}}"#);
        assert_eq!(urls(&json).unwrap(), [page]);
    }

    #[test]
    fn nullable_base_is_supported_for_current_full_urls() {
        assert_eq!(
            urls(r#"{"baseUrl":null,"items":[{"url":"https://img.example.net/page.jpg"}]}"#).unwrap(),
            ["https://img.example.net/page.jpg"]
        );
    }

    #[test]
    fn legacy_base_and_relative_pages_keep_their_order() {
        assert_eq!(
            urls(r#"{"baseUrl":"https://img.example.net/","items":[{"url":"/one.jpg"},{"url":"two.jpg"}]}"#).unwrap(),
            ["https://img.example.net/one.jpg", "https://img.example.net/two.jpg"]
        );
    }

    #[test]
    fn protocol_relative_page_uses_its_own_https_host() {
        assert_eq!(
            urls(r#"{"baseUrl":"https://old.example.net","items":[{"url":"//new.example.net/page.jpg"}]}"#).unwrap(),
            ["https://new.example.net/page.jpg"]
        );
    }

    #[test]
    fn invalid_relative_or_unsafe_pages_are_not_returned_as_a_partial_chapter() {
        for page in ["/missing-base.jpg", "http://img.example.net/p.jpg", "https://",
                     "https://user:secret@img.example.net/p.jpg", "javascript:alert(1)"] {
            let json = serde_json::json!({"items":[{"url":"https://img.example.net/one.jpg"},{"url":page}]}).to_string();
            assert!(urls(&json).is_err(), "{page}");
        }
    }

    #[test]
    fn empty_chapter_is_an_explicit_error() {
        assert!(urls(r#"{"items":[]}"#).is_err());
    }
}
