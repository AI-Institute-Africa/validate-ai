import { describe, expect, it } from "vitest";
import { MAX_BYTES, MAX_FILES, MAX_TEXT, validateFiles } from "./validateFiles";

const f = (name: string, size = 1000, type = "image/png") => ({ name, size, type });

describe("validateFiles", () => {
  it("accepts supported files", () => {
    expect(validateFiles([], [f("a.png"), f("b.pdf", 10, "application/pdf")]).errors).toEqual([]);
  });
  it("skips duplicates by name and size", () => {
    const a = f("a.png");
    expect(validateFiles([a], [f("a.png")]).files).toHaveLength(1);
  });
  it("rejects oversize, empty and unsupported files", () => {
    const r = validateFiles([], [f("big.png", MAX_BYTES + 1), f("e.png", 0), f("x.exe", 5, "application/x-msdownload")]);
    expect(r.files).toHaveLength(0);
    expect(r.errors).toHaveLength(3);
  });
  it("caps the number of files", () => {
    const many = Array.from({ length: MAX_FILES + 2 }, (_, i) => f(`p${i}.png`, 100 + i));
    const r = validateFiles([], many);
    expect(r.files).toHaveLength(MAX_FILES);
    expect(r.errors).toHaveLength(2);
  });
  it("limits pasted text", () => {
    expect(validateFiles([], [], "x".repeat(MAX_TEXT + 1)).errors).toHaveLength(1);
  });
  it("accepts HEIC with an empty mime type by extension", () => {
    expect(validateFiles([], [f("IMG_1.HEIC", 50, "")]).files).toHaveLength(1);
  });
});

describe("every everyday type is accepted", () => {
  const ok = ["a.gif", "a.bmp", "a.tif", "a.tiff", "a.avif", "a.svg", "a.xlsx", "a.pptx", "a.odt", "a.ods", "a.odp", "a.epub", "a.rtf", "a.html", "a.csv", "a.md", "a.txt", "a.eml", "A.JPG"];
  it("by name when the browser gives no type", () => {
    for (const name of ok) expect(validateFiles([], [f(name, 50, "")]).files, name).toHaveLength(1);
  });
  it("by type when the name has no extension", () => {
    for (const type of ["image/avif", "image/gif", "image/bmp", "image/tiff", "image/svg+xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "text/html", "application/rtf"]) {
      expect(validateFiles([], [f("noext", 50, type)]).files, type).toHaveLength(1);
    }
  });
  it("still refuses programs and archives", () => {
    for (const name of ["a.exe", "a.zip", "a.js", "a.mp4", "a.mp3"]) expect(validateFiles([], [f(name, 50, "")]).files, name).toHaveLength(0);
  });
  it("tells a payer with an old .doc or .xls what to do, in a translatable way", () => {
    const r = validateFiles([], [f("old.doc", 50, "application/msword"), f("old.xls", 50, "")]);
    expect(r.files).toHaveLength(0);
    expect(r.issues.map((i) => i.key)).toEqual(["file.err.legacy", "file.err.legacy"]);
    expect(r.errors[0]).toMatch(/save it as a PDF/i);
  });
});
