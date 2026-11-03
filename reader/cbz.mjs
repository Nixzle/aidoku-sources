// Read-only streaming CBZ reader: ZIP central directory is inspected before
// extracting a single image. No remote requests and no content persistence.
const MAX_ITEMS = 12000;
const MAX_PAGES = 5000;
const MAX_IMAGE = 32 * 1024 * 1024;
const MAX_ARCHIVE = 2 * 1024 * 1024 * 1024;
const EXTENSIONS = /\.(png|jpe?g|webp|gif|avif)$/i;
const read32 = (view, off) => view.getUint32(off, true);
const read16 = (view, off) => view.getUint16(off, true);
const decoder = new TextDecoder("utf-8");

export async function scanCbz(file) {
  if (!file || !Number.isSafeInteger(file.size) || file.size < 22 || file.size > MAX_ARCHIVE || typeof file.slice !== "function") {
    throw Error("Choose a CBZ/ZIP file smaller than 2 GB.");
  }
  const base = Math.max(0, file.size - 65557);
  const tail = new Uint8Array(await file.slice(base, file.size).arrayBuffer());
  const tailView = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
  let end = -1;
  for (let i = tail.length - 22; i >= 0; i--) {
    if (read32(tailView, i) === 0x06054b50 && i + 22 + read16(tailView, i + 20) === tail.length) { end = i; break; }
  }
  if (end < 0) throw Error("CBZ file has no valid ZIP directory.");
  if (read16(tailView, end + 4) !== 0 || read16(tailView, end + 6) !== 0 ||
      read16(tailView, end + 8) !== read16(tailView, end + 10)) {
    throw Error("Multipart ZIP files are not supported.");
  }
  const count = read16(tailView, end + 10);
  const directorySize = read32(tailView, end + 12);
  const directoryStart = read32(tailView, end + 16);
  if (count > MAX_ITEMS || count === 0xffff || directorySize === 0xffffffff || directoryStart === 0xffffffff ||
      directoryStart + directorySize > base + end || directorySize > 12 * 1024 * 1024) {
    throw Error("CBZ archive is oversized or uses unsupported ZIP64.");
  }
  const central = new Uint8Array(await file.slice(directoryStart, directoryStart + directorySize).arrayBuffer());
  const view = new DataView(central.buffer, central.byteOffset, central.byteLength);
  let pos = 0;
  const pages = [];
  for (let i = 0; i < count; i++) {
    if (pos + 46 > central.length || read32(view, pos) !== 0x02014b50) throw Error("Damaged CBZ directory.");
    const flags = read16(view, pos + 8), method = read16(view, pos + 10);
    const compressed = read32(view, pos + 20), uncompressed = read32(view, pos + 24);
    const n = read16(view, pos + 28), extra = read16(view, pos + 30), comment = read16(view, pos + 32);
    const localOffset = read32(view, pos + 42);
    const after = pos + 46 + n + extra + comment;
    if (after > central.length || localOffset >= directoryStart) throw Error("Invalid CBZ entry bounds.");
    const name = decoder.decode(central.subarray(pos + 46, pos + 46 + n));
    if (EXTENSIONS.test(name) && !/(^\/|\\|(^|\/)\.\.(\/|$))/.test(name) && !name.startsWith("__MACOSX/")) {
      if (flags & 1) throw Error("Encrypted CBZ images are unsupported.");
      if (method !== 0 && method !== 8) throw Error("Unsupported CBZ compression.");
      if (uncompressed === 0 || uncompressed > MAX_IMAGE || compressed > MAX_IMAGE || compressed === 0) {
        throw Error("A CBZ image exceeds the safe 32 MB limit.");
      }
      if (uncompressed / compressed > 400) throw Error("Suspicious CBZ compression ratio.");
      pages.push({ name, localOffset, compressed, uncompressed, method });
      if (pages.length > MAX_PAGES) throw Error("CBZ contains too many images.");
    }
    pos = after;
  }
  if (!pages.length) throw Error("CBZ has no supported image pages.");
  pages.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  return pages;
}

export async function readCbzImage(file, page) {
  const headerBytes = new Uint8Array(await file.slice(page.localOffset, page.localOffset + 30).arrayBuffer());
  if (headerBytes.length !== 30) throw Error("Truncated CBZ entry.");
  const header = new DataView(headerBytes.buffer);
  if (read32(header, 0) !== 0x04034b50) throw Error("Damaged CBZ local header.");
  if (read16(header, 8) !== page.method) throw Error("CBZ entry compression mismatch.");
  const start = page.localOffset + 30 + read16(header, 26) + read16(header, 28);
  if (start + page.compressed > file.size) throw Error("Truncated CBZ image.");
  const compressed = await file.slice(start, start + page.compressed).arrayBuffer();
  let content;
  if (page.method === 0) content = new Blob([compressed]);
  else {
    if (typeof DecompressionStream === "undefined") throw Error("This browser lacks ZIP decompression. Update Safari or Chrome.");
    const reader = new Blob([compressed]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader();
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > MAX_IMAGE || total > page.uncompressed) {
          await reader.cancel();
          throw Error("CBZ image decompressed beyond its declared size.");
        }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    content = new Blob(chunks);
  }
  if (content.size !== page.uncompressed || content.size > MAX_IMAGE) throw Error("Corrupt or oversized CBZ image.");
  const ext = page.name.split(".").at(-1).toLowerCase();
  const mime = { jpg:"image/jpeg",jpeg:"image/jpeg",png:"image/png",webp:"image/webp",gif:"image/gif",avif:"image/avif" }[ext];
  return new Blob([content], { type: mime });
}
