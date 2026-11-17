// The one list of files a payer may send as proof. It mirrors what the server reads
// (backend/app/intake/files.py); the server still checks the real contents, never the name.

export const IMAGE_TYPES = [
  "image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/avif",
  "image/gif", "image/bmp", "image/tiff", "image/svg+xml", "image/jp2", "image/vnd.adobe.photoshop",
  "image/x-adobe-dng", "image/x-canon-cr2", "image/x-nikon-nef", "image/x-sony-arw",
];
export const DOCUMENT_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.oasis.opendocument.text",
  "application/vnd.oasis.opendocument.spreadsheet",
  "application/vnd.oasis.opendocument.presentation",
  "application/epub+zip",
  "application/rtf",
  "text/rtf",
  "text/html",
  "message/rfc822",
  "text/plain",
  "text/markdown",
  "text/csv",
];

export const ALLOWED_TYPES = new Set([...IMAGE_TYPES, ...DOCUMENT_TYPES]);

export const EXTENSIONS = [
  "png", "jpg", "jpeg", "jfif", "webp", "heic", "heif", "avif", "gif", "bmp", "tif", "tiff", "svg", "jp2", "j2k",
  "dng", "cr2", "cr3", "nef", "arw", "raf", "orf", "rw2", "psd", "ai",
  "pdf", "docx", "xlsx", "pptx", "odt", "ods", "odp", "epub", "rtf", "html", "htm",
  "eml", "txt", "md", "csv", "tsv",
];
export const ALLOWED_EXT = new RegExp(`\\.(${EXTENSIONS.join("|")})$`, "i");

/** Value for <input type="file" accept=...>: browsers use both the type and the extension. */
export const ACCEPT = ["image/*", ...EXTENSIONS.map((e) => `.${e}`), ...DOCUMENT_TYPES].join(",");

/** Old binary Office files cannot be read safely: tell the payer what to do instead. */
export const LEGACY_EXT = /\.(doc|xls|ppt)$/i;
