import { parseAidokuFile } from "./plist.mjs";

export const SCHEMA = "sanctum-reader-library-v1";
const MAX_ENTRIES = 20000;
const MAX_TEXT = 320;
const now = () => new Date().toISOString();
const limitText = value => String(value ?? "").trim().slice(0, MAX_TEXT);
export const safeHttpUrl = (raw, sourceId = "") => {
  if (typeof raw !== "string" || raw.length > 2048) return "";
  try {
    let url;
    if (raw.startsWith("/") && (sourceId === "en.comix" || sourceId === "en.comixws")) {
      url = new URL(raw, sourceId === "en.comix" ? "https://comix.to" : "https://comix.ws");
    } else {
      url = new URL(raw);
    }
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return "";
    if (sourceId === "en.comix" && !["comix.to", "comix.ws"].includes(url.hostname)) return "";
    if (sourceId === "en.comixws" && url.hostname !== "comix.ws") return "";
    // Never persist OAuth fragments, signed image parameters or login tokens.
    url.hash = "";
    const sensitive = /^(access[_-]?token|id[_-]?token|refresh[_-]?token|auth|authorization|apikey|api[_-]?key|session|signature|sig|jwt|password|secret)$/i;
    for (const key of [...url.searchParams.keys()]) if (sensitive.test(key)) url.searchParams.delete(key);
    return url.toString();
  } catch { return ""; }
};
const timestamp = value => {
  const ms = value instanceof Date ? value.getTime() : typeof value === "number" ? value : Date.parse(value ?? "");
  return Number.isFinite(ms) && ms > 0 ? new Date(ms).toISOString() : "";
};
const key = (source, id) => String(source ?? "") + "::" + String(id ?? "");
const validEntry = input => {
  if (!input || typeof input !== "object") return null;
  const title = limitText(input.title);
  if (!title) return null;
  const sourceId = limitText(input.sourceId || "manual");
  const id = limitText(input.id || "manual::" + title.toLowerCase());
  const url = safeHttpUrl(input.url, sourceId);
  const chapterUrl = safeHttpUrl(input.chapterUrl, sourceId);
  const chapter = limitText(input.chapter);
  return {
    id, sourceId, title, url, chapterUrl, chapter,
    page: Number.isInteger(input.page) ? Math.max(0, Math.min(100000, input.page)) : 0,
    completed: Boolean(input.completed),
    addedAt: timestamp(input.addedAt) || now(),
    updatedAt: timestamp(input.updatedAt) || now(),
    provenance: limitText(input.provenance || "manual"),
    notes: limitText(input.notes)
  };
};

export function fromAidoku(input) {
  const backup = parseAidokuFile(input);
  const entries = Array.isArray(backup.library) && backup.library.length
    ? backup.library : Array.isArray(backup.manga) ? backup.manga.map(x => ({ mangaId: x.id, sourceId: x.sourceId, dateAdded: backup.date })) : [];
  if (entries.length > MAX_ENTRIES) throw Error("Too many library entries. Please export a smaller backup.");
  const manga = new Map((backup.manga || []).map(x => [key(x.sourceId, x.id), x]));
  const chapters = new Map((backup.chapters || []).map(x => [key(x.sourceId, x.id), x]));
  const lastRead = new Map();
  for (const h of backup.history || []) {
    const id = key(h.sourceId, h.mangaId);
    if (!h.mangaId || !h.sourceId) continue;
    const prior = lastRead.get(id);
    if (!prior || (timestamp(h.dateRead) || "") > (timestamp(prior.dateRead) || "")) lastRead.set(id, h);
  }
  const normalized = [];
  for (const record of entries) {
    const sourceId = String(record.sourceId || "");
    const mangaId = String(record.mangaId || record.id || "");
    if (!sourceId || !mangaId) continue;
    const item = manga.get(key(sourceId, mangaId)) || record;
    const h = lastRead.get(key(sourceId, mangaId));
    const chapter = h && chapters.get(key(sourceId, h.chapterId));
    const book = validEntry({
      id: key(sourceId, mangaId),
      sourceId,
      title: item.title || mangaId,
      url: item.url,
      chapterUrl: chapter?.url,
      chapter: chapter?.chapter != null ? String(chapter.chapter) : chapter?.title || "",
      page: h?.progress,
      completed: h?.completed,
      addedAt: record.dateAdded || backup.date,
      updatedAt: h?.dateRead || record.lastOpened || backup.date,
      provenance: "aidoku"
    });
    if (book) normalized.push(book);
  }
  return { entries: normalized, count: normalized.length, version: limitText(backup.version), from: "Aidoku backup" };
}

export function makeManual(title, url, sourceId = "manual") {
  const normalized = safeHttpUrl(url, sourceId);
  if (!normalized) throw Error("Enter a valid http(s) reading URL without embedded credentials.");
  const name = limitText(title);
  if (!name) throw Error("Enter a title.");
  return validEntry({
    id: key(sourceId, normalized),
    title: name, sourceId,
    url: normalized, provenance: "manual"
  });
}

export function mergeEntries(existing, incoming) {
  const map = new Map();
  for (const item of existing) {
    const clean = validEntry(item);
    if (clean) map.set(clean.id, clean);
  }
  for (const item of incoming) {
    const clean = validEntry(item);
    if (!clean) continue;
    const old = map.get(clean.id);
    if (!old || clean.updatedAt > old.updatedAt) {
      map.set(clean.id, old && !clean.url ? { ...clean, url: old.url } : clean);
    }
  }
  if (map.size > MAX_ENTRIES) throw Error("Library exceeds 20,000 titles.");
  return [...map.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.title.localeCompare(b.title));
}

export function exportLibrary(entries) {
  const clean = mergeEntries([], entries);
  return JSON.stringify({
    schema: SCHEMA,
    exportedAt: now(),
    privacy: "User-owned metadata only; no source credentials, manga images or website cookies",
    entries: clean
  }, null, 2);
}

export function importLibrary(text) {
  if (typeof text !== "string" || text.length > 10 * 1024 * 1024) throw Error("Invalid or oversized library snapshot.");
  let data;
  try { data = JSON.parse(text); }
  catch { throw Error("The library snapshot is not valid JSON."); }
  if (data?.schema !== SCHEMA || !Array.isArray(data.entries) || data.entries.length > MAX_ENTRIES) {
    throw Error("This is not a Sanctum Reader library backup.");
  }
  return mergeEntries([], data.entries);
}

export function markRead(item, chapter, page, completed = false) {
  return validEntry({ ...item, chapter: limitText(chapter), page: Math.max(0, Math.trunc(Number(page) || 0)), completed, updatedAt: now() });
}
