import { ALLOWED_EXT, ALLOWED_TYPES, LEGACY_EXT, RAW_EXT } from "./fileTypes";

// Client-side pre-flight for proof uploads. The server enforces the same limits; this only
// saves a round trip. Limits mirror docs/configuration.md.

export const MAX_FILES = 5;
export const MAX_BYTES = 10 * 1024 * 1024;
// camera RAW is large by nature, so only it may be bigger (mirrors POPS_MAX_RAW_UPLOAD_BYTES)
export const MAX_RAW_BYTES = 80 * 1024 * 1024;
export const MAX_TOTAL_BYTES = 120 * 1024 * 1024;

export const limitFor = (name: string) => (RAW_EXT.test(name) ? MAX_RAW_BYTES : MAX_BYTES);
export const MAX_TEXT = 20_000;


export type FileLike = { name: string; size: number; type: string };

export function fileKey(f: FileLike): string {
  return `${f.name}:${f.size}`;
}

export type Issue = { key: string; params: Record<string, string> };

/** Drop files already in the list (same name and size), then check count, size and type.
 *  `errors` are English sentences; `issues` carry a translation key and values so the screen can show
 *  the same message in the payer's language. */
export function validateFiles<T extends FileLike>(existing: T[], incoming: T[], text = ""): { files: T[]; errors: string[]; issues: Issue[] } {
  const errors: string[] = [];
  const issues: Issue[] = [];
  const fail = (msg: string, key: string, params: Record<string, string>) => {
    errors.push(msg);
    issues.push({ key, params });
  };
  const seen = new Set(existing.map(fileKey));
  const files = [...existing];
  for (const f of incoming) {
    if (seen.has(fileKey(f))) continue;
    if (LEGACY_EXT.test(f.name)) {
      fail(`${f.name}: old .doc, .xls and .ppt files cannot be read safely. Save it as a PDF or as .docx, .xlsx, .pptx and send that.`, "file.err.legacy", { name: f.name });
      continue;
    }
    if (!ALLOWED_TYPES.has(f.type) && !ALLOWED_EXT.test(f.name)) {
      fail(`${f.name}: this file type is not supported. Use a photo, scan, PDF, Word, Excel or PowerPoint file, an email, or plain text.`, "file.err.type", { name: f.name });
      continue;
    }
    const limit = limitFor(f.name);
    if (f.size > limit) {
      fail(`${f.name}: larger than ${limit / 1024 / 1024} MB.`, "file.err.size", { name: f.name, mb: String(limit / 1024 / 1024) });
      continue;
    }
    if (files.reduce((n, x) => n + x.size, 0) + f.size > MAX_TOTAL_BYTES) {
      fail(`${f.name}: together the files may not be more than ${MAX_TOTAL_BYTES / 1024 / 1024} MB.`, "file.err.total", { name: f.name, mb: String(MAX_TOTAL_BYTES / 1024 / 1024) });
      continue;
    }
    if (f.size === 0) {
      fail(`${f.name}: the file is empty.`, "file.err.empty", { name: f.name });
      continue;
    }
    if (files.length >= MAX_FILES) {
      fail(`You can add up to ${MAX_FILES} files. ${f.name} was not added.`, "file.err.count", { max: String(MAX_FILES), name: f.name });
      continue;
    }
    seen.add(fileKey(f));
    files.push(f);
  }
  if (text.length > MAX_TEXT) errors.push(`Pasted text is longer than ${MAX_TEXT.toLocaleString()} characters.`);
  return { files, errors, issues };
}
