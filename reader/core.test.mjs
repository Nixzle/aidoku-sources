import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseAidokuFile, parseBinaryPlist } from "./plist.mjs";
import { fromAidoku, safeHttpUrl, makeManual, mergeEntries, exportLibrary, importLibrary, markRead } from "./core.mjs";
const fixture = readFileSync(new URL("./test-fixtures/sample.aib", import.meta.url));

test("reads a real binary property list generated with Python plistlib", () => {
  const backup = parseAidokuFile(fixture);
  assert.equal(backup.version, "0.9");
  assert.equal(backup.library.length, 2);
  assert.equal(backup.manga[1].title, "A Manga – Café");
  assert.ok(backup.date instanceof Date);
  assert.equal(backup.settings.ComixExamplePrivateToken, "SECRET_DO_NOT_EXPORT");
});
test("extracts titles, latest chapters and read positions", () => {
  const data = fromAidoku(fixture);
  assert.equal(data.count, 2);
  const comix = data.entries.find(x => x.sourceId === "en.comix");
  assert.equal(comix.title, "Second Half");
  assert.equal(comix.chapter, "1");
  assert.equal(comix.page, 7);
  assert.match(comix.chapterUrl, /^https:\/\/comix\.to\/title\/x55j7-second-half\/8927229-chapter-1$/);
  assert.equal(comix.id, "en.comix::x55j7");
});
test("never exports source credentials or unneeded private backup data", () => {
  const data = fromAidoku(fixture);
  const json = exportLibrary(data.entries);
  assert.ok(!json.includes("SECRET_DO_NOT_EXPORT"));
  assert.ok(!json.includes("ComixExamplePrivateToken"));
  assert.equal(importLibrary(json).length, 2);
});
test("supports Aidoku JSON format as well as binary plist", () => {
  const sample = readFileSync(new URL("./test-fixtures/sample.json", import.meta.url));
  assert.equal(fromAidoku(sample).count, 1);
});
test("rejects unsafe or cross-origin Comix URLs", () => {
  for (const url of ["javascript:alert(1)", "file:///etc/passwd", "https://user:pass@comix.to/title/x", "https://comix.to.evil.example/title/x", "https://127.0.0.1/title/x"]) {
    assert.equal(safeHttpUrl(url, "en.comix"), "");
  }
  assert.equal(safeHttpUrl("/title/x55j7-second-half", "en.comix"), "https://comix.to/title/x55j7-second-half");
});
test("strips tracking secrets from stored reading links", () => {
  const safe = safeHttpUrl("https://comix.to/title/abc?lang=en&access_token=PRIVATE&signature=SECRET#jwt-secret", "en.comix");
  assert.equal(safe, "https://comix.to/title/abc?lang=en");
});
test("preserves later progress when importing an older Aidoku backup", () => {
  const item = fromAidoku(fixture).entries.find(x => x.sourceId === "en.comix");
  const newer = { ...item, chapter: "20", page: 4, updatedAt: "2026-11-03T05:00:00.000Z" };
  const merged = mergeEntries([newer], [item]);
  assert.equal(merged[0].chapter, "20");
});
test("allows intentional manual progress updates and JSON roundtrip", () => {
  const item = makeManual("A new title", "https://comix.to/title/abc", "en.comix");
  const updated = markRead(item, "14", 9, false);
  assert.equal(updated.chapter, "14");
  assert.equal(updated.page, 9);
  assert.equal(importLibrary(exportLibrary([updated]))[0].page, 9);
});
test("rejects malformed backups and foreign snapshots without modification", () => {
  assert.throws(() => parseAidokuFile(new Uint8Array([1,2,3])), /supported/);
  assert.throws(() => parseBinaryPlist(fixture.subarray(0, 22)), /Invalid/);
  assert.throws(() => importLibrary('{"entries":[{"title":"fake"}]}'), /not a Sanctum Reader/);
  assert.throws(() => importLibrary("{invalid"), /not valid JSON/);
});
test("rejects unsafe links in imported snapshots", () => {
  const entry = { id: "bad", title: "Example", sourceId: "manual", url: "javascript:alert(1)", updatedAt: "2026-11-03T00:00:00Z" };
  const result = importLibrary(JSON.stringify({ schema: "sanctum-reader-library-v1", entries: [entry] }));
  assert.equal(result[0].url, "");
});
test("max-entry limits and binary size limits prevent unbounded imports", () => {
  assert.throws(() => parseBinaryPlist(new Uint8Array(49 * 1024 * 1024)), /Invalid/);
  const records = Array.from({length: 20001}, (_, i) => ({ title: "Book " + i, id: String(i) }));
  assert.throws(() => mergeEntries([], records), /20,000/);
});
