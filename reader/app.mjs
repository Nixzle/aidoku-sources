import { fromAidoku, makeManual, mergeEntries, exportLibrary, importLibrary, markRead } from "./core.mjs";
import { scanCbz, readCbzImage } from "./cbz.mjs";

const byId = id => document.getElementById(id);
let entries = [];
let selectedId = "";
let visibleLimit = 80;
let db = null;
let toastHandle = 0;
let cbzFile = null, cbzPages = [], cbzIndex = 0, cbzUrl = "", cbzEntryId = "";
let cbzLoadId = 0;

function showToast(message) {
  const el = byId("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastHandle);
  toastHandle = setTimeout(() => { el.hidden = true; }, 6000);
}

function openDB() {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in globalThis)) return reject(Error("IndexedDB not available"));
    const request = indexedDB.open("sanctum-reader-library", 1);
    request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains("state")) request.result.createObjectStore("state"); };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || Error("Unable to open device storage"));
    request.onblocked = () => reject(Error("Device storage is busy in another tab"));
  });
}
function state(mode, action) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("state", mode);
    const request = action(tx.objectStore("state"));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || Error("Storage failed"));
    tx.onabort = () => reject(tx.error || Error("Storage transaction failed"));
  });
}
async function persist() {
  if (!db) { showToast("Device storage unavailable. Export your library before closing."); return; }
  try { await state("readwrite", store => store.put(entries, "library")); }
  catch { showToast("Could not save locally. Export a backup to avoid losing changes."); }
}
async function apply(incoming) {
  const after = mergeEntries(entries, incoming);
  entries = after;
  await persist();
  render();
}

function textEl(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  el.textContent = text;
  return el;
}
function shortSource(sourceId) {
  if (sourceId === "en.comix") return "Comix";
  if (sourceId === "en.comixws") return "Comix WS";
  if (sourceId === "manual") return "Added manually";
  return sourceId.replace(/^(en|multi)\./, "");
}
function isComix(book) {
  return book.sourceId === "en.comix" || book.sourceId === "en.comixws" ||
    /^https:\/\/(comix\.to|comix\.ws)\//.test(book.url);
}
function render() {
  byId("statTotal").textContent = String(entries.length);
  byId("statInProgress").textContent = String(entries.filter(x => x.chapter || x.page > 0).length);
  byId("statComix").textContent = String(entries.filter(isComix).length);
  const q = byId("searchInput").value.toLowerCase().trim();
  const source = byId("sourceFilter").value;
  const matches = entries.filter(x => {
    if (source === "en.comix" && !isComix(x)) return false;
    if (source === "other" && isComix(x)) return false;
    return !q || x.title.toLowerCase().includes(q) || x.sourceId.toLowerCase().includes(q);
  });
  byId("emptyState").hidden = entries.length > 0;
  const shelf = byId("library");
  shelf.replaceChildren();
  if (!matches.length && entries.length) {
    shelf.append(textEl("p", "micro", "No titles match this search."));
    return;
  }
  for (const book of matches.slice(0, visibleLimit)) {
    const card = textEl("article", "book", "");
    const top = textEl("div", "book-header", "");
    const title = textEl("h3", "book-title", book.title);
    const badge = textEl("span", "source", shortSource(book.sourceId));
    top.append(title, badge);
    const current = book.sourceId === "local-file" ? (book.page ? "Page " + book.page + " saved" : "Open this file to start") : book.chapter ? "Chapter " + book.chapter + (book.page ? " · Page " + book.page : "") : "No chapter recorded";
    const progress = textEl("div", "book-meta", current);
    const actions = textEl("div", "book-actions", "");
    const link = book.chapterUrl || book.url;
    if (book.sourceId === "local-file") {
      const open = textEl("button", "", "Open local file");
      open.type = "button";
      open.addEventListener("click", () => byId("cbzFile").click());
      actions.append(open);
    }
    if (link) {
      const read = textEl("a", "", "Continue reading ↗");
      read.href = link;
      read.target = "_blank";
      read.rel = "noopener noreferrer";
      read.title = "Open on " + new URL(link).hostname + " (the original website)";
      actions.append(read);
    }
    const update = textEl("button", "", "Update progress");
    update.type = "button";
    update.addEventListener("click", () => {
      selectedId = book.id;
      byId("progressTitle").textContent = book.title;
      byId("chapterInput").value = book.chapter;
      byId("pageInput").value = String(book.page);
      byId("completedInput").checked = book.completed;
      byId("progressDialog").showModal();
    });
    actions.append(update);
    const del = textEl("button", "remove", "Remove");
    del.type = "button";
    del.title = "Remove this title from this device only";
    del.addEventListener("click", async () => {
      if (!confirm('Remove "' + book.title + '" from this device’s catalogue? Your original Aidoku library is unaffected.')) return;
      entries = entries.filter(x => x.id !== book.id);
      await persist();
      render();
    });
    actions.append(del);
    card.append(top, progress, actions);
    shelf.append(card);
  }
  if (visibleLimit < matches.length) {
    const more = textEl("button", "secondary", "Show more titles (" + (matches.length - visibleLimit) + " remaining)");
    more.type = "button";
    more.addEventListener("click", () => { visibleLimit += 80; render(); });
    shelf.append(more);
  }
}

function saveFile(name, contents, type) {
  const blob = new Blob([contents], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 5000);
}
function dateName() {
  return new Date().toISOString().slice(0, 10);
}

byId("importAidoku").addEventListener("click", () => byId("aidokuFile").click());
byId("emptyImport").addEventListener("click", () => byId("aidokuFile").click());
byId("importJsonBtn").addEventListener("click", () => byId("jsonFile").click());
byId("exportBtn").addEventListener("click", () => {
  saveFile("sanctum-reader-" + dateName() + ".json", exportLibrary(entries), "application/json");
  showToast("Portable backup exported. Transfer the file to your other device to merge there.");
});
byId("aidokuFile").addEventListener("change", async e => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  if (file.size > 48 * 1024 * 1024) return showToast("Backup exceeds the 48 MB file safety limit.");
  try {
    const data = fromAidoku(await file.arrayBuffer());
    if (!data.count) return showToast("No library titles found in the Aidoku backup.");
    await apply(data.entries);
    showToast("Imported " + data.count + " Aidoku titles. Existing newer progress was retained.");
  } catch (error) { showToast("Import failed: " + error.message); }
});
byId("jsonFile").addEventListener("change", async e => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) return showToast("Library snapshot exceeds 10 MB.");
  try {
    const imported = importLibrary(await file.text());
    await apply(imported);
    showToast("Merged " + imported.length + " saved titles.");
  } catch (error) { showToast("Import failed: " + error.message); }
});
byId("addToggle").addEventListener("click", () => {
  byId("addForm").hidden = !byId("addForm").hidden;
  if (!byId("addForm").hidden) byId("newTitle").focus();
});
byId("cancelAdd").addEventListener("click", () => { byId("addForm").hidden = true; });
byId("addForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const url = byId("newUrl").value;
    const hostname = new URL(url).hostname.toLowerCase();
    const source = ["comix.to", "comix.ws"].includes(hostname) ? "en.comix" : "manual";
    await apply([makeManual(byId("newTitle").value, url, source)]);
    byId("addForm").reset();
    byId("addForm").hidden = true;
    showToast("Title saved on this device.");
  } catch (error) { showToast(error.message); }
});
byId("closeDialog").addEventListener("click", () => byId("progressDialog").close());
byId("progressForm").addEventListener("submit", async e => {
  e.preventDefault();
  const book = entries.find(x => x.id === selectedId);
  if (book) {
    await apply([markRead(book, byId("chapterInput").value, Number(byId("pageInput").value), byId("completedInput").checked)]);
    showToast("Progress saved locally. Export to carry this catalogue to another device.");
  }
  byId("progressDialog").close();
});
byId("searchInput").addEventListener("input", () => { visibleLimit = 80; render(); });
byId("sourceFilter").addEventListener("change", () => { visibleLimit = 80; render(); });

// The CBZ viewer operates only on a user-selected local File object.
async function showCbzPage(position) {
  if (!cbzFile || position < 0 || position >= cbzPages.length) return;
  const id = ++cbzLoadId, current = position;
  byId("cbzCounter").textContent = "Opening page " + (current + 1) + "…";
  try {
    const blob = await readCbzImage(cbzFile, cbzPages[current]);
    if (id !== cbzLoadId) return;
    const url = URL.createObjectURL(blob);
    const previous = cbzUrl;
    cbzUrl = url;
    byId("cbzImage").src = url;
    if (previous) URL.revokeObjectURL(previous);
    cbzIndex = current;
    byId("cbzCounter").textContent = "Page " + (current + 1) + " / " + cbzPages.length;
    byId("cbzPrevious").disabled = current === 0;
    byId("cbzNext").disabled = current === cbzPages.length - 1;
    const book = entries.find(x => x.id === cbzEntryId);
    if (book) await apply([markRead(book, book.chapter, current + 1, book.completed)]);
  } catch (error) { showToast("Cannot display this CBZ page: " + error.message); }
}
byId("openCbz").addEventListener("click", () => byId("cbzFile").click());
byId("cbzFile").addEventListener("change", async event => {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  try {
    const pages = await scanCbz(file);
    const id = "local-file::" + file.name + "::" + file.size;
    let current = entries.find(x => x.id === id);
    if (!current) {
      await apply([{
        id, title: file.name.replace(/\.(cbz|zip)$/i, ""),
        sourceId: "local-file", url: "", chapter: "", page: 0,
        addedAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
        provenance: "local-file", notes: ""
      }]);
      current = entries.find(x => x.id === id);
    }
    cbzFile = file;
    cbzPages = pages;
    cbzEntryId = id;
    cbzIndex = Math.max(0, Math.min((current?.page || 1) - 1, cbzPages.length - 1));
    byId("cbzTitle").textContent = current?.title || file.name;
    byId("cbzDialog").showModal();
    await showCbzPage(cbzIndex);
  } catch (error) { showToast("Could not open the CBZ file: " + error.message); }
});
byId("cbzPrevious").addEventListener("click", () => showCbzPage(cbzIndex - 1));
byId("cbzNext").addEventListener("click", () => showCbzPage(cbzIndex + 1));
byId("cbzClose").addEventListener("click", () => byId("cbzDialog").close());
byId("cbzDialog").addEventListener("close", () => {
  ++cbzLoadId;
  if (cbzUrl) URL.revokeObjectURL(cbzUrl);
  cbzUrl = "";
  byId("cbzImage").removeAttribute("src");
  cbzFile = null;
  cbzPages = [];
});
document.addEventListener("keydown", event => {
  if (!byId("cbzDialog").open) return;
  if (event.key === "ArrowRight") { event.preventDefault(); showCbzPage(cbzIndex + 1); }
  if (event.key === "ArrowLeft") { event.preventDefault(); showCbzPage(cbzIndex - 1); }
});

(async () => {
  try {
    db = await openDB();
    const saved = await state("readonly", store => store.get("library"));
    entries = mergeEntries([], Array.isArray(saved) ? saved : []);
  } catch { showToast("Local database storage unavailable. You can import and export, but changes may not persist."); }
  render();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js").catch(() => {});
})();
