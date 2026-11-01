//! Bounded chapter-list resume. Only validated, recent metadata is reused.
use aidoku::alloc::{String, Vec};
use serde::{Deserialize, Serialize, de::DeserializeOwned};

const MAX_BYTES: usize = 1024 * 1024;
const MAX_ITEMS: usize = 8_000;
const MAX_PAGES: i32 = 1_000;
const RESUME_SECONDS: i64 = 60 * 60;
const COMPLETE_SECONDS: i64 = 120;

#[derive(Serialize, Deserialize)]
pub struct ChapterCheckpoint<T> {
    manga_key: String,
    first_page_ids: Vec<i32>,
    total_pages: i32,
    pub completed_page: i32,
    updated_at: i64,
    pub chapters: Vec<T>,
}

impl<T> ChapterCheckpoint<T> {
    pub fn new(key: String, first_page_ids: Vec<i32>, total_pages: i32, chapters: Vec<T>, now: i64) -> Self {
        Self { manga_key: key, first_page_ids, total_pages, completed_page: 1, updated_at: now, chapters }
    }

    pub fn advance(&mut self, page: i32, total_pages: i32, items: Vec<T>, now: i64) -> bool {
        if page != self.completed_page + 1 || total_pages != self.total_pages
            || page > self.total_pages {
            return false;
        }
        self.chapters.extend(items);
        self.completed_page = page;
        self.updated_at = now;
        true
    }

    pub fn is_complete(&self) -> bool { self.completed_page == self.total_pages }
}

impl<T: DeserializeOwned> ChapterCheckpoint<T> {
    pub fn resume(raw: &str, key: &str, first_page_ids: &[i32], total_pages: i32, now: i64) -> Option<Self> {
        if raw.len() > MAX_BYTES { return None; }
        let checkpoint: Self = serde_json::from_str(raw).ok()?;
        let age = now.checked_sub(checkpoint.updated_at)?;
        let max_age = if checkpoint.is_complete() { COMPLETE_SECONDS } else { RESUME_SECONDS };
        if age < 0 || age > max_age || checkpoint.manga_key != key
            || checkpoint.first_page_ids.as_slice() != first_page_ids
            || checkpoint.first_page_ids.len() > 100
            || checkpoint.total_pages != total_pages || !(1..=MAX_PAGES).contains(&checkpoint.total_pages)
            || checkpoint.completed_page < 1 || checkpoint.completed_page > total_pages
            || checkpoint.chapters.len() < first_page_ids.len() || checkpoint.chapters.len() > MAX_ITEMS {
            return None;
        }
        Some(checkpoint)
    }
}

impl<T: Serialize> ChapterCheckpoint<T> {
    pub fn encode(&self) -> Option<String> {
        if self.chapters.len() > MAX_ITEMS || !(1..=MAX_PAGES).contains(&self.total_pages)
            || self.completed_page < 1 || self.completed_page > self.total_pages { return None; }
        let json = serde_json::to_string(self).ok()?;
        (json.len() <= MAX_BYTES).then_some(json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aidoku::alloc::vec;
    #[derive(Serialize, Deserialize, Debug, PartialEq)]
    struct Entry { id: i32 }
    fn sample(now: i64) -> ChapterCheckpoint<Entry> {
        ChapterCheckpoint::new("book".into(), vec![7, 8], 3, vec![Entry{id:7},Entry{id:8}], now)
    }
    #[test]
    fn resume_only_matching_series_and_first_page() {
        let checkpoint = sample(100).encode().unwrap();
        assert!(ChapterCheckpoint::<Entry>::resume(&checkpoint, "book", &[7,8], 3, 101).is_some());
        assert!(ChapterCheckpoint::<Entry>::resume(&checkpoint, "other", &[7,8], 3, 101).is_none());
        assert!(ChapterCheckpoint::<Entry>::resume(&checkpoint, "book", &[8,7], 3, 101).is_none());
        assert!(ChapterCheckpoint::<Entry>::resume(&checkpoint, "book", &[7,8], 4, 101).is_none());
    }
    #[test]
    fn partial_progress_survives_interruptions() {
        let mut checkpoint = sample(100);
        assert!(checkpoint.advance(2, 3, vec![Entry{id:9}], 120));
        let raw = checkpoint.encode().unwrap();
        let mut resumed = ChapterCheckpoint::<Entry>::resume(&raw,"book",&[7,8],3,130).unwrap();
        assert_eq!(resumed.completed_page, 2);
        assert!(resumed.advance(3,3,vec![Entry{id:10}],140));
        assert_eq!(resumed.chapters.iter().map(|x|x.id).collect::<Vec<_>>(),vec![7,8,9,10]);
        assert!(resumed.is_complete());
    }
    #[test]
    fn reject_out_of_order_or_changed_pagination_without_mutation() {
        let mut cp = sample(100);
        assert!(!cp.advance(3,3,vec![Entry{id:9}],110));
        assert!(!cp.advance(2,4,vec![Entry{id:9}],110));
        assert_eq!(cp.completed_page,1);
        assert_eq!(cp.chapters.len(),2);
    }
    #[test]
    fn reuse_window_is_bounded_and_clock_rollback_is_invalid() {
        let partial = sample(100).encode().unwrap();
        assert!(ChapterCheckpoint::<Entry>::resume(&partial,"book",&[7,8],3,3700).is_some());
        assert!(ChapterCheckpoint::<Entry>::resume(&partial,"book",&[7,8],3,3701).is_none());
        assert!(ChapterCheckpoint::<Entry>::resume(&partial,"book",&[7,8],3,99).is_none());
        let mut complete = sample(100);
        assert!(complete.advance(2,3,vec![],105));
        assert!(complete.advance(3,3,vec![],110));
        let raw = complete.encode().unwrap();
        assert!(ChapterCheckpoint::<Entry>::resume(&raw,"book",&[7,8],3,230).is_some());
        assert!(ChapterCheckpoint::<Entry>::resume(&raw,"book",&[7,8],3,231).is_none());
    }
    #[test]
    fn reject_corrupt_or_excessive_cache() {
        assert!(ChapterCheckpoint::<Entry>::resume("{","book",&[7,8],3,100).is_none());
        let mut cp = sample(100);
        cp.first_page_ids = (0..101).collect();
        let raw = cp.encode().unwrap();
        assert!(ChapterCheckpoint::<Entry>::resume(&raw,"book",&cp.first_page_ids,3,100).is_none());
        assert!(ChapterCheckpoint::<Entry>::resume(&"x".repeat(MAX_BYTES+1),"book",&[7,8],3,100).is_none());
    }
}