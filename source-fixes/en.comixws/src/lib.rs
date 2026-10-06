#![no_std]
use aidoku::{
	Chapter, DeepLinkHandler, DeepLinkResult, FilterValue, HashMap, Home, HomeComponent,
	HomeLayout, HomePartialResult, ImageRequestProvider, Link, LinkValue, Listing, ListingProvider,
	Manga, MangaPageResult, MangaWithChapter, NotificationHandler, Page, PageContent, PageContext,
	Result, Source, WebLoginHandler,
	alloc::{String, Vec, string::ToString, vec},
	helpers::uri::{QueryParameters, encode_uri_component},
	imports::{
		net::Request,
		std::{current_date, send_partial_result},
	},
	prelude::*,
};
use core::cell::RefCell;

mod helpers;
mod models;
mod settings;
mod web;
#[path = "../../shared/transport.rs"]
mod transport;

use crate::helpers::create_request_get;
use crate::settings::VERIFY_KEY;
use models::*;
use web::*;

const BASE_URL: &str = "https://comix.ws";
const API_URL: &str = "https://comix.ws/api/v1";
const COMIX_ORIGINS: &[&str] = &[BASE_URL];
const COMIX_ASSET_ORIGINS: &[&str] = &["https://comix.ws/", "https://static.comix.ws/"];

const CONTENT_TYPES: &[&str] = &["manga", "manhwa", "manhua", "other"];
const MAX_CHAPTER_PAGES: i32 = 1_000;
// adult, boys love, ecchi, girls love, hentai, smut
const NSFW_GENRE_IDS: &[&str] = &["87264", "8", "87265", "13", "87266", "87268"];

fn is_allowed_asset_url(url: &str) -> bool {
	COMIX_ASSET_ORIGINS
		.iter()
		.any(|origin| url.starts_with(origin))
}

struct Comix {
	web_view: RefCell<ComixWebView>,
}

impl Source for Comix {
	fn new() -> Self {
		Self {
			web_view: RefCell::new(ComixWebView::new()),
		}
	}

	fn get_search_manga_list(
		&self,
		query: Option<String>,
		page: i32,
		filters: Vec<FilterValue>,
	) -> Result<MangaPageResult> {
		let mut web_view = self.web_view.borrow_mut();

		let mut qs = QueryParameters::new();
		qs.push("page", Some(&page.to_string()));
		if query.is_some() {
			qs.push("keyword", query.as_deref());
		}

		let mut hidden_types = {
			let types = settings::hidden_types();
			if types.is_empty() { None } else { Some(types) }
		};
		let mut hidden_terms = settings::hidden_terms();

		let mut has_sort_filter = false;

		for filter in filters {
			match filter {
				FilterValue::Text { id, value } => {
					let url = format!(
						"{API_URL}/terms?type={id}&keyword={}&limit=1",
						encode_uri_component(value)
					);
					let response = web_view.send_request(&url)?;
					web_view
						.decode_json_owned::<TermResponse>(&response)?
						.result
						.items
						.first()
						.map(|t| t.id)
						.ok_or_else(|| error!("No matching {id}s"))?;
					qs.push(&format!("{id}s[]"), Some(&id.to_string()));
				}
				FilterValue::Sort {
					id,
					index,
					ascending,
				} => {
					qs.push(
						&format!(
							"{id}[{}]",
							match index {
								0 => "relevance",
								1 => "chapter_updated_at",
								2 => "created_at",
								3 => "title",
								4 => "year",
								5 => "score",
								6 => "views_7d",
								7 => "views_30d",
								8 => "views_90d",
								9 => "views_total",
								10 => "follows_total",
								_ => "relevance",
							}
						),
						Some(if (index == 3 && !ascending) || (index != 3 && ascending) {
							"asc"
						} else {
							"desc"
						}),
					);
					has_sort_filter = true;
				}
				FilterValue::Select { id, value } => {
					qs.push(&id, Some(&value));
				}
				FilterValue::MultiSelect {
					id,
					included,
					excluded,
				} => {
					// if any content type is set manually, skip our content type filters
					if id == "types[]" {
						hidden_types = None;
					}
					for value in included {
						// if a hidden term is manually included in filters, skip hiding it
						if id == "genres[]" {
							let id_num = value.parse::<i32>().unwrap_or_default();
							if let Some(pos) = hidden_terms.iter().position(|&x| x == id_num) {
								hidden_terms.swap_remove(pos);
								continue;
							}
							qs.push("genres_in[]", Some(&value));
						} else {
							qs.push(&id, Some(&value));
						}
					}
					for value in excluded {
						// make sure hidden terms aren't added to query params twice
						if id == "genres[]" {
							if hidden_terms.contains(&value.parse().unwrap_or_default()) {
								continue;
							}

							qs.push("genres_ex[]", Some(&value));
						} else {
							qs.push(&id, Some(&format!("-{value}")));
						}
					}
				}
				_ => continue,
			}
		}

		if !has_sort_filter {
			qs.push("order[relevance]", Some("desc"));
		}

		if let Some(hidden_types) = hidden_types {
			for &typ in CONTENT_TYPES {
				if !hidden_types.iter().any(|s| s.as_str() == typ) {
					qs.push("types[]", Some(typ));
				}
			}
		}

		for term in hidden_terms {
			qs.push("genres_ex[]", Some(&term.to_string()));
		}

		if settings::hide_nsfw() {
			for genre_id in NSFW_GENRE_IDS {
				qs.push("genres_ex[]", Some(genre_id));
			}
		}

		let url = format!("{API_URL}/manga?{qs}");
		let response = web_view.send_request(&url)?;
		web_view
			.decode_json_owned::<SearchResponse>(&response)
			.map(Into::into)
	}

	fn get_manga_update(
		&self,
		mut manga: Manga,
		needs_details: bool,
		needs_chapters: bool,
	) -> Result<Manga> {
		let mut web_view = self.web_view.borrow_mut();

		if needs_details {
			let url = format!(
				"{API_URL}/manga/{}?includes[]=demographic\
									&includes[]=genre\
									&includes[]=theme\
									&includes[]=author\
									&includes[]=artist\
									&includes[]=publisher",
				manga.key
			);
			let response = web_view.send_request(&url)?;
			let json: SingleMangaResponse = web_view.decode_json_owned(&response)?;

			manga.copy_from(json.result.into_detailed_manga());

			if needs_chapters {
				send_partial_result(&manga);
			}
		}

		if needs_chapters {
			let limit = 100;
			let mut page = 1;
			let deduplicate = settings::dedupchapter();
			let mut chapter_map: HashMap<String, ComixChapter> = HashMap::new();
			let mut chapter_list: Vec<ComixChapter> = Vec::new();
			let mut previous_response_page = 0;

			loop {
				if page > MAX_CHAPTER_PAGES {
					bail!("Comix chapter pagination exceeded the safety limit")
				}
				let mut params = QueryParameters::new();
				params.push("limit", Some(limit.to_string().as_str()));
				params.push("page", Some(page.to_string().as_str()));
				params.push("order[number]", Some("desc"));

				let url = format!("{API_URL}/manga/{}/chapters?{params}", manga.key);
				let response = web_view.send_request(&url)?;
				let res = web_view.decode_json_owned::<ChapterDetailsResponse>(&response)?;
				let response_page = res.result.meta.page;
				let last_page = res.result.meta.last_page;
				if response_page <= previous_response_page || last_page < response_page {
					bail!("Comix chapter pagination did not advance")
				}
				previous_response_page = response_page;

				let items = res.result.items;
				if items.is_empty() && response_page < last_page {
					bail!("Comix chapter pagination returned an empty intermediate page")
				}

				if deduplicate {
					for item in items {
						helpers::dedup_insert(&mut chapter_map, item);
					}
				} else {
					chapter_list.extend(items);
				}

				if response_page >= last_page {
					break;
				}

				page += 1;
			}

			let mut chapters: Vec<Chapter> = if deduplicate {
				chapter_map.into_values().map(Into::into).collect()
			} else {
				chapter_list.into_iter().map(Into::into).collect()
			};

			if deduplicate {
				chapters.sort_by(|a, b| {
					b.chapter_number
						.partial_cmp(&a.chapter_number)
						.unwrap_or(core::cmp::Ordering::Equal)
				});
			}

			manga.chapters = Some(chapters);
		}

		Ok(manga)
	}

	fn get_page_list(&self, _manga: Manga, chapter: Chapter) -> Result<Vec<Page>> {
		let mut web_view = self.web_view.borrow_mut();
		let url = format!("{API_URL}/chapters/{}", chapter.key);
		let response = web_view.send_request(&url)?;
		let json: ChapterResponse = web_view.decode_json_owned(&response)?;

		let Some(result) = json.result else {
			bail!("Missing chapter")
		};

		let base_url = result.pages.base_url.trim_end_matches('/');
		let mut pages = Vec::with_capacity(result.pages.items.len());
		for page in result.pages.items {
			let url = if page.url.starts_with("http") {
				page.url
			} else {
				format!("{base_url}/{}", page.url.trim_start_matches('/'))
			};
			if !is_allowed_asset_url(&url) {
				bail!("Rejected unexpected Comix WS image host")
			}
			pages.push(Page {
				content: PageContent::url(url),
				..Default::default()
			});
		}
		Ok(pages)
	}
}

fn home_layout() -> HomeLayout {
	HomeLayout {
		components: vec![
			HomeComponent {
				title: Some("Most Recent Popular".into()),
				subtitle: None,
				value: aidoku::HomeComponentValue::empty_scroller(),
			},
			HomeComponent {
				title: Some("Most Follows New Comics".into()),
				subtitle: None,
				value: aidoku::HomeComponentValue::empty_scroller(),
			},
			HomeComponent {
				title: Some("Latest Updates (Hot)".into()),
				subtitle: None,
				value: aidoku::HomeComponentValue::empty_scroller(),
			},
			HomeComponent {
				title: Some("Recently Added".into()),
				subtitle: None,
				value: aidoku::HomeComponentValue::empty_manga_chapter_list(),
			},
		],
	}
}

fn empty_home_scroller(title: &str) -> HomeComponent {
	HomeComponent {
		title: Some(title.into()),
		subtitle: None,
		value: aidoku::HomeComponentValue::Scroller {
			entries: Vec::new(),
			listing: Some(Listing {
				id: title.into(),
				name: title.into(),
				..Default::default()
			}),
		},
	}
}

fn empty_home_recent() -> HomeComponent {
	let title = "Recently Added";
	HomeComponent {
		title: Some(title.into()),
		subtitle: None,
		value: aidoku::HomeComponentValue::MangaChapterList {
			page_size: None,
			entries: Vec::new(),
			listing: Some(Listing {
				id: title.into(),
				name: title.into(),
				..Default::default()
			}),
		},
	}
}

fn send_home_scroller(
	web_view: &mut ComixWebView,
	url: &str,
	title: &str,
	hidden_types: &[String],
	hidden_terms: &[i32],
) -> Result<HomeComponent> {
	let response = web_view.send_request(url)?;
	let entries = web_view
		.decode_json_owned::<SearchResponse>(&response)?
		.result
		.items
		.into_iter()
		.filter(|m| !m.is_hidden(hidden_types, hidden_terms))
		.map(|m| {
			let manga = Manga::from(m);
			Link {
				title: manga.title.clone(),
				subtitle: None,
				image_url: manga.cover.clone(),
				value: Some(LinkValue::Manga(manga)),
			}
		})
		.collect();
	Ok(HomeComponent {
		title: Some(title.into()),
		subtitle: None,
		value: aidoku::HomeComponentValue::Scroller {
			entries,
			listing: Some(Listing {
				id: title.into(),
				name: title.into(),
				..Default::default()
			}),
		},
	})
}

fn send_home_recent(
	web_view: &mut ComixWebView,
	url: &str,
	hidden_types: &[String],
	hidden_terms: &[i32],
) -> Result<HomeComponent> {
	let response = web_view.send_request(url)?;
	let entries = web_view
		.decode_json_owned::<SearchResponse>(&response)?
		.result
		.items
		.into_iter()
		.filter(|m| !m.is_hidden(hidden_types, hidden_terms))
		.map(|m| {
			let chapter_number = m.latest_chapter;
			let manga = Manga::from(m);
			MangaWithChapter {
				manga,
				chapter: Chapter {
					chapter_number,
					..Default::default()
				},
			}
		})
		.collect();
	let title = "Recently Added";
	Ok(HomeComponent {
		title: Some(title.into()),
		subtitle: None,
		value: aidoku::HomeComponentValue::MangaChapterList {
			page_size: None,
			entries,
			listing: Some(Listing {
				id: title.into(),
				name: title.into(),
				..Default::default()
			}),
		},
	})
}

fn emit_home_result(
	result: Result<HomeComponent>,
	failed_component: HomeComponent,
	layout_sent: &mut bool,
	pending_failures: &mut Vec<HomeComponent>,
	successful_sections: &mut usize,
	first_error: &mut Option<String>,
) {
	match result {
		Ok(component) => {
			if !*layout_sent {
				send_partial_result(&HomePartialResult::Layout(home_layout()));
				*layout_sent = true;
				for failed in pending_failures.drain(..) {
					send_partial_result(&HomePartialResult::Component(failed));
				}
			}
			send_partial_result(&HomePartialResult::Component(component));
			*successful_sections += 1;
		}
		Err(error) => {
			if first_error.is_none() {
				*first_error = Some(error.to_string());
			}
			if *layout_sent {
				send_partial_result(&HomePartialResult::Component(failed_component));
			} else {
				pending_failures.push(failed_component);
			}
		}
	}
}

impl Home for Comix {
	fn get_home(&self) -> Result<HomeLayout> {
		let extra_qs = if settings::hide_nsfw() {
			NSFW_GENRE_IDS
				.iter()
				.map(|id| format!("&genres_ex[]={id}"))
				.collect::<String>()
		} else {
			Default::default()
		};

		let hidden_types = settings::hidden_types();
		let hidden_terms = settings::hidden_terms();
		let mut web_view = self.web_view.borrow_mut();
		let mut layout_sent = false;
		let mut pending_failures = Vec::new();
		let mut successful_sections = 0;
		let mut first_error = None;

		for (url, title) in [
			(
				format!("{API_URL}/manga/top?type=trending&days=1&limit=20{extra_qs}"),
				"Most Recent Popular",
			),
			(
				format!("{API_URL}/manga/top?type=follows&days=1&limit=20{extra_qs}"),
				"Most Follows New Comics",
			),
			(
				format!(
					"{API_URL}/manga?scope=hot&limit=30&order[chapter_updated_at]=desc&page=1{extra_qs}"
				),
				"Latest Updates (Hot)",
			),
		] {
			let result =
				send_home_scroller(&mut web_view, &url, title, &hidden_types, &hidden_terms);
			emit_home_result(
				result,
				empty_home_scroller(title),
				&mut layout_sent,
				&mut pending_failures,
				&mut successful_sections,
				&mut first_error,
			);
		}

		let recent_url =
			format!("{API_URL}/manga?order[created_at]=desc&limit=10&page=1{extra_qs}");
		let result =
			send_home_recent(&mut web_view, &recent_url, &hidden_types, &hidden_terms);
		emit_home_result(
			result,
			empty_home_recent(),
			&mut layout_sent,
			&mut pending_failures,
			&mut successful_sections,
			&mut first_error,
		);

		if successful_sections == 0 {
			bail!(
				"Unable to load Comix home: {}",
				first_error.unwrap_or_else(|| "no section returned data".into())
			);
		}

		Ok(HomeLayout::default())
	}
}

impl ListingProvider for Comix {
	fn get_manga_list(&self, listing: Listing, page: i32) -> Result<MangaPageResult> {
		let trending = |types: Vec<String>| {
			self.get_search_manga_list(
				None,
				page,
				vec![
					FilterValue::Sort {
						id: "order".into(),
						index: 8, // most views 1mo
						ascending: false,
					},
					FilterValue::MultiSelect {
						id: "types[]".into(),
						included: types,
						excluded: Default::default(),
					},
				],
			)
		};

		fn get_listing_page(comix: &Comix, url: &str) -> Result<MangaPageResult> {
			let extra_qs = if settings::hide_nsfw() {
				NSFW_GENRE_IDS
					.iter()
					.map(|id| format!("&genres_ex[]={id}"))
					.collect::<String>()
			} else {
				Default::default()
			};
			let hidden_types = settings::hidden_types();
			let hidden_terms = settings::hidden_terms();
			let url = format!("{url}{extra_qs}");
			let mut web_view = comix.web_view.borrow_mut();

			let response = web_view.send_request(&url)?;
			web_view
				.decode_json_owned::<SearchResponse>(&response)
				.map(|r| r.result.into_filtered(&hidden_types, &hidden_terms))
		}

		match listing.id.as_str() {
			"Trending Webtoon" => trending(vec!["manhua".into(), "manhwa".into()]),
			"Trending Manga" => trending(vec!["manga".into()]),

			"Most Recent Popular" => get_listing_page(
				self,
				&format!("{API_URL}/manga/top?type=trending&days=1&limit=50"),
			),
			"Most Follows New Comics" => get_listing_page(
				self,
				&format!("{API_URL}/manga/top?type=follows&days=1&limit=50"),
			),

			"Latest Updates (Hot)" => get_listing_page(
				self,
				&format!(
					"{API_URL}/manga?scope=hot&limit=30&order[chapter_updated_at]=desc&page={page}"
				),
			),
			"Recently Added" => get_listing_page(
				self,
				&format!("{API_URL}/manga?order[created_at]=desc&limit=30&page={page}"),
			),

			_ => bail!("Unknown listing"),
		}
	}
}

impl ImageRequestProvider for Comix {
	fn get_image_request(&self, url: String, _context: Option<PageContext>) -> Result<Request> {
		if !is_allowed_asset_url(&url) {
			bail!("Rejected unexpected Comix WS image host")
		}
		// Comix image hosts reject Origin and Referer. Aidoku's plain GET does
		// not add either header, while retaining the explicit host allowlist.
		create_request_get(&url)
	}
}

impl NotificationHandler for Comix {
	fn handle_notification(&self, notification: String) {
		if notification == "resetFilters" {
			settings::reset_filters();
		}
	}
}

impl DeepLinkHandler for Comix {
	fn handle_deep_link(&self, url: String) -> Result<Option<DeepLinkResult>> {
		let Some(path) = url.strip_prefix(&format!("{BASE_URL}/")) else {
			return Ok(None);
		};

		// ex: https://comix.ws/title/pvry-one-piece
		// ex: https://comix.ws/title/pvry-one-piece/5498414-chapter-1

		let mut segments = path.split('/');

		if let (Some("title"), Some(manga_segment)) = (segments.next(), segments.next()) {
			// ex: pvry-one-piece -> pvry
			let manga_key = manga_segment.split('-').next().unwrap_or(manga_segment);

			if let Some(chapter_segment) = segments.next() {
				// ex: 5498414-chapter-1 -> 5498414
				let chapter_key = chapter_segment.split('-').next().unwrap_or("");
				return Ok(Some(DeepLinkResult::Chapter {
					manga_key: manga_key.to_string(),
					key: chapter_key.to_string(),
				}));
			} else {
				return Ok(Some(DeepLinkResult::Manga {
					key: manga_key.to_string(),
				}));
			}
		}

		Ok(None)
	}
}

const VERIFY_COOKIE_KEY: &str = "waf_pass";

impl WebLoginHandler for Comix {
	fn handle_web_login(&self, key: String, cookies: HashMap<String, String>) -> Result<bool> {
		if key == VERIFY_KEY {
			// This is verifying button not to be confused with actual login button.
			// We need to intercept waf_pass cookie so that we can pass the checks.
			// This will not log you in even if you do the login page afterward.
			let verified = cookies.get(VERIFY_COOKIE_KEY).is_some_and(|pass| {
				let Some((timestamp, _)) = pass.split_once('.') else {
					return false;
				};
				let current_timestamp = current_date();
				current_timestamp - timestamp.parse::<i64>().unwrap_or(0) < 30 * 60
			});
			if verified {
				self.web_view.borrow_mut().reset();
			}
			return Ok(verified);
		}

		Ok(false)
	}
}

register_source!(
	Comix,
	Home,
	ListingProvider,
	ImageRequestProvider,
	NotificationHandler,
	DeepLinkHandler,
	WebLoginHandler
);
