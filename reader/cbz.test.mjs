import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scanCbz, readCbzImage } from "./cbz.mjs";
const bytes = readFileSync(new URL("./test-fixtures/sample.cbz", import.meta.url));
const file = new Blob([bytes]);

test("lists only images and sorts comic pages naturally", async () => {
  const pages = await scanCbz(file);
  assert.deepEqual(pages.map(p => p.name), ["chapter/page2.png", "chapter/page10.png"]);
});
test("decompresses only the selected image using browser-native deflate", async () => {
  const pages = await scanCbz(file);
  const blob = await readCbzImage(file, pages[0]);
  assert.equal(blob.type, "image/png");
  const content = Buffer.from(await blob.arrayBuffer());
  assert.equal(content.toString("hex", 0, 8), "89504e470d0a1a0a");
});
test("rejects invalid or oversized archives", async () => {
  await assert.rejects(scanCbz(new Blob(["not zip"])), /smaller than|directory/);
  const broken = new Blob([bytes.subarray(0, bytes.length - 12)]);
  await assert.rejects(scanCbz(broken), /directory/);
});
test("does not load an image whose compressed data is outside the file", async () => {
  const pages = await scanCbz(file);
  await assert.rejects(readCbzImage(file, { ...pages[0], compressed: 50000 }), /Truncated/);
});
