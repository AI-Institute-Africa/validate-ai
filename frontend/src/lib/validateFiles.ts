// Client-side pre-flight for proof uploads. The server enforces the same limits; this only
// saves a round trip. Limits mirror docs/configuration.md.

export const MAX_FILES = 5;
export const MAX_BYTES = 10 * 1024 * 1024;
export const MAX_TEXT = 20_000;

const ALLOWED_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/heic",
  "image/heif",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
const ALLOWED_EXT = /\.(png|jpe?g|webp|heic|heif|pdf|docx)$/i;

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
    if (!ALLOWED_TYPES.has(f.type) && !ALLOWED_EXT.test(f.name)) {
      fail(`${f.name}: this file type is not supported. Use a photo, PDF or Word file.`, "file.err.type", { name: f.name });
      continue;
    }
    if (f.size > MAX_BYTES) {
      fail(`${f.name}: larger than ${MAX_BYTES / 1024 / 1024} MB.`, "file.err.size", { name: f.name, mb: String(MAX_BYTES / 1024 / 1024) });
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
