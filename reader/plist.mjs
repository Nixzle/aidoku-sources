// Read-only, bounded Apple binary property-list decoder for Aidoku .aib exports.
// Nothing here sends files or credentials anywhere.
const MAX_FILE = 48 * 1024 * 1024;
const MAX_OBJECTS = 350_000;
const MAX_DEPTH = 72;
const textDecoder = new TextDecoder();

export function parseAidokuFile(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_FILE) throw Error("Backup size is invalid or exceeds 48 MB.");
  let result;
  if (bytes.byteLength >= 8 && textDecoder.decode(bytes.subarray(0, 8)) === "bplist00") {
    result = parseBinaryPlist(bytes);
  } else {
    try { result = JSON.parse(textDecoder.decode(bytes)); }
    catch { throw Error("Not a supported Aidoku .aib plist or JSON backup."); }
  }
  if (!result || typeof result !== "object" || Array.isArray(result) ||
      (!Array.isArray(result.library) && !Array.isArray(result.manga))) {
    throw Error("The file does not contain an Aidoku library.");
  }
  return result;
}

export function parseBinaryPlist(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  const len = bytes.byteLength;
  if (len < 40 || len > MAX_FILE || textDecoder.decode(bytes.subarray(0, 8)) !== "bplist00") {
    throw Error("Invalid binary property list.");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, len);
  const tail = len - 32;
  const offsetSize = bytes[tail + 6], refSize = bytes[tail + 7];
  if (![1, 2, 4, 8].includes(offsetSize) || ![1, 2, 4, 8].includes(refSize)) throw Error("Unsupported plist size.");
  const readUInt = (pos, n) => {
    if (pos < 0 || n < 1 || n > 8 || pos + n > len) throw Error("Truncated plist integer.");
    let value = 0n;
    for (let i = 0; i < n; i++) value = (value << 8n) | BigInt(bytes[pos + i]);
    if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw Error("Oversized plist integer.");
    return Number(value);
  };
  const count = readUInt(tail + 8, 8);
  const root = readUInt(tail + 16, 8);
  const tableStart = readUInt(tail + 24, 8);
  if (count < 1 || count > MAX_OBJECTS || root >= count ||
      tableStart < 8 || tableStart + count * offsetSize > tail) throw Error("Invalid plist object table.");
  const offsets = Array.from({ length: count }, (_, i) => readUInt(tableStart + i * offsetSize, offsetSize));
  if (offsets.some(o => o < 8 || o >= tableStart)) throw Error("Object position outside plist data.");
  const cache = new Map(), active = new Set();
  const readLength = (offset, nibble) => {
    if (nibble !== 15) return { size: nibble, at: offset + 1 };
    if (offset + 1 >= tableStart) throw Error("Invalid plist length.");
    const marker = bytes[offset + 1];
    if ((marker >> 4) !== 1) throw Error("Invalid extended plist length.");
    const n = 2 ** (marker & 15);
    if (n > 8) throw Error("Oversized plist length.");
    return { size: readUInt(offset + 2, n), at: offset + 2 + n };
  };
  const get = (index, depth = 0) => {
    if (cache.has(index)) return cache.get(index);
    if (index >= count || depth > MAX_DEPTH || active.has(index)) throw Error("Invalid or cyclic plist reference.");
    active.add(index);
    const pos = offsets[index], marker = bytes[pos], kind = marker >> 4, low = marker & 15;
    let result;
    const { size, at } = readLength(pos, low);
    const bounded = (unit = 1) => {
      if (size > MAX_OBJECTS || at + size * unit > tableStart) throw Error("Plist object length exceeds bounds.");
    };
    if (kind === 0) {
      if (marker === 0) result = null;
      else if (marker === 8) result = false;
      else if (marker === 9) result = true;
      else throw Error("Unknown plist simple value.");
    } else if (kind === 1 || kind === 8) {
      const n = 2 ** low;
      if (n > 8) throw Error("Unsupported plist integer width.");
      result = readUInt(pos + 1, n);
    } else if (kind === 2) {
      const n = 2 ** low;
      if (n !== 4 && n !== 8 || pos + 1 + n > tableStart) throw Error("Unsupported plist real.");
      result = n === 4 ? view.getFloat32(pos + 1, false) : view.getFloat64(pos + 1, false);
    } else if (kind === 3) {
      if (low !== 3 || pos + 9 > tableStart) throw Error("Invalid plist date.");
      result = new Date((view.getFloat64(pos + 1, false) + 978307200) * 1000);
      if (Number.isNaN(result.getTime())) throw Error("Invalid plist date.");
    } else if (kind === 4) {
      bounded();
      result = { binaryBytes: size }; // Never carry authentication or data blobs into the reader library.
    } else if (kind === 5) {
      bounded();
      result = textDecoder.decode(bytes.subarray(at, at + size));
    } else if (kind === 6) {
      bounded(2);
      let s = "";
      for (let i = 0; i < size; i++) s += String.fromCharCode(view.getUint16(at + i * 2, false));
      result = s;
    } else if (kind === 10 || kind === 13) {
      bounded(kind === 13 ? refSize * 2 : refSize);
      if (kind === 10) {
        result = [];
        for (let i = 0; i < size; i++) result.push(get(readUInt(at + i * refSize, refSize), depth + 1));
      } else {
        result = Object.create(null);
        for (let i = 0; i < size; i++) {
          const key = get(readUInt(at + i * refSize, refSize), depth + 1);
          if (typeof key !== "string") throw Error("Non-string plist dictionary key.");
          // Property keys stay inert, even for "__proto__" or "constructor".
          result[key] = get(readUInt(at + (size + i) * refSize, refSize), depth + 1);
        }
      }
    } else {
      throw Error("Unsupported plist object type " + kind);
    }
    cache.set(index, result);
    active.delete(index);
    return result;
  };
  return get(root);
}
