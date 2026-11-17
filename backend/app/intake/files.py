"""File validation, hashing and image preparation (pipeline stage 1, error layer 1)."""

import email
import email.policy
import hashlib
import html.parser
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

import imagehash
from PIL import ExifTags, Image, ImageDraw, ImageFont, ImageOps, ImageSequence

Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard

_AVIF = False
try:
    from PIL import features as _features

    _AVIF = bool(_features.check("avif"))
except Exception:  # pragma: no cover  # noqa: BLE001
    _AVIF = False

try:  # iPhone photos (HEIC/HEIF)
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF = True
except ImportError:  # pragma: no cover
    HEIF = False

MAX_PAGES = 10  # pages read per document; longer documents are flagged for review
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT = "text/plain"  # pasted SMS / WhatsApp / banking-app text
EML = "message/rfc822"  # a forwarded email, with its attachments
MAX_TEXT_CHARS = 20_000
_EMAIL_HEADER = re.compile(
    rb"^(From|To|Subject|Date|Received|Return-Path|MIME-Version|Message-ID|Delivered-To|"
    rb"DKIM-Signature|X-[A-Za-z-]+):",
    re.M | re.I,
)
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}
_AVIF_BRANDS = {b"avif", b"avis"}

# more everyday formats. Spreadsheets, slides, OpenDocument, e-books, RTF and HTML are read as
# text (and any pictures inside them); none is ever executed or shown by a browser engine.
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ODT = "application/vnd.oasis.opendocument.text"
ODS = "application/vnd.oasis.opendocument.spreadsheet"
ODP = "application/vnd.oasis.opendocument.presentation"
EPUB = "application/epub+zip"
RTF = "application/rtf"
HTML = "text/html"
SVG = "image/svg+xml"
RAW = "image/x-raw"  # camera RAW (DNG, CR2, CR3, NEF, ARW, RAF, ORF, RW2): its embedded photo
PSD = "image/vnd.adobe.photoshop"
JP2 = "image/jp2"
# types whose "image" is drawn from text or vectors: pixel forensics mean nothing for them
RENDERED_TYPES = {TEXT, EML, HTML, RTF, XLSX, PPTX, ODT, ODS, ODP, EPUB, SVG}
# easy to type up or edit: a bank or mobile-money app does not issue its receipts like this
# a browser would run these if it opened them, so the original is only ever served as a download
ACTIVE_CONTENT_TYPES = {HTML, SVG, RTF, EPUB}
EDITABLE_TYPES = {DOCX, XLSX, PPTX, ODT, ODS, ODP, RTF, HTML, EPUB, PSD}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old binary Word / Excel / PowerPoint
MAX_TEXT_KEPT = 200_000  # characters of document text kept for the readers
_OFFICE_ZIP = {
    "word/document.xml": DOCX,
    "xl/workbook.xml": XLSX,
    "ppt/presentation.xml": PPTX,
}
_MIMETYPES = {ODT, ODS, ODP, EPUB}

# Magic numbers: we trust file signatures, never the client's content type or extension.
SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF-", "application/pdf"),
]


class RejectedFile(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sniff(data: bytes) -> str:
    for sig, ctype in SIGNATURES:
        if data.startswith(sig):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS and HEIF:
        return "image/heic"
    if data[4:8] == b"ftyp" and data[8:12] in _AVIF_BRANDS and _AVIF:
        return "image/avif"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM" and len(data) > 26 and data[6:10] == b"\x00\x00\x00\x00":
        return "image/bmp"
    if data[:8] == b"8BPS\x00\x01\x00\x00" or data[:4] == b"8BPS":
        return PSD
    if data[:12] == b"\x00\x00\x00\x0cjP  \r\n\x87\n" or data[:4] == b"\xff\x4f\xff\x51":
        return JP2
    if data[:4] == b"%!PS" or data[:4] == b"\xc5\xd0\xd3\xc6":
        raise RejectedFile(
            "POSTSCRIPT",
            "PostScript and old EPS/AI files can contain programs and are not accepted: export it "
            "as PDF, PNG or JPEG and send that",
        )
    if _is_raw(data):
        return RAW
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data.startswith(_OLE_MAGIC):
        raise RejectedFile(
            "LEGACY_OFFICE",
            "old .doc, .xls and .ppt files cannot be read safely: save it as PDF or as "
            ".docx / .xlsx / .pptx and send that",
        )
    if data.startswith(b"{\\rtf"):
        return RTF
    if data.startswith(b"PK\x03\x04"):
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
            names = set(zf.namelist())
            mimetype = (
                zf.read("mimetype").decode(errors="ignore").strip() if "mimetype" in names else ""
            )
        except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
            raise RejectedFile("CORRUPT_FILE", "the document could not be opened") from exc
        for marker, ctype in _OFFICE_ZIP.items():
            if marker in names:
                return ctype
        if mimetype in _MIMETYPES:
            return mimetype
    if b"\x00" not in data[:4096]:
        head = data[:4096]
        low = head.lstrip().lower()
        if b"<svg" in low[:2048] and (
            low.startswith(b"<?xml") or low.startswith(b"<svg") or low.startswith(b"<!doctype svg")
        ):
            return SVG
        if low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<html" in low[:1024]:
            return HTML
        if len(_EMAIL_HEADER.findall(head)) >= 3 and re.search(rb"^From:", head, re.M | re.I):
            return EML
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = ""
        printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
        if text.strip() and len(text) <= MAX_TEXT_CHARS and printable / len(text) > 0.97:
            return TEXT
    raise RejectedFile(
        "UNSUPPORTED_TYPE",
        "accepted evidence: photos and scans (PNG, JPEG, WEBP, HEIC, AVIF, GIF, BMP, TIFF, "
        "JPEG 2000, SVG, camera RAW, Photoshop), PDF, Word, Excel and PowerPoint (.docx, .xlsx, "
        ".pptx), OpenDocument, RTF, HTML, e-books (.epub), forwarded emails (.eml) and pasted text",
    )


@dataclass
class PreparedFile:
    content_type: str
    sha256: str
    image: Image.Image  # first page / the image, RGB, orientation corrected
    phash: str
    meta: dict[str, Any] = field(default_factory=dict)
    preview_png: bytes = b""
    pages: list[Image.Image] = field(default_factory=list)  # every page/image to read
    page_texts: list[str] = field(default_factory=list)  # digital text per page (PDF/DOCX)
    # preview is the pages stacked vertically; (y0, h) of each page as fractions of the stack
    page_layout: list[tuple[float, float]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(t for t in self.page_texts if t)


def _render_pdf(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise RejectedFile("CORRUPT_FILE", "the PDF could not be opened") from exc
    if doc.needs_pass:
        raise RejectedFile("ENCRYPTED_PDF", "password-protected PDFs are not accepted")
    if doc.page_count == 0:
        raise RejectedFile("CORRUPT_FILE", "the PDF has no pages")
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    meta["page_count"] = doc.page_count
    # each incremental save appends a new trailer: more than one %%EOF means the PDF was edited
    # after it was first written (banks' generated statements are written once)
    meta["eof_markers"] = data.count(b"%%EOF")
    pages, texts = [], []
    for n in range(min(doc.page_count, MAX_PAGES)):
        page = doc.load_page(n)
        texts.append(page.get_text().strip())
        pix = page.get_pixmap(dpi=150 if doc.page_count > 3 else 200)
        pages.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    meta["has_text"] = any(texts)
    meta["pages_read"] = len(pages)
    return pages, texts, {"pdf": meta}


def _read_docx(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    """Word documents: the text (paragraphs and tables) plus any embedded screenshots."""
    from docx import Document

    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if len(infos) > 2000 or sum(i.file_size for i in infos) > 60 * 1024 * 1024:
        raise RejectedFile("CORRUPT_FILE", "the document is too large when unpacked")
    names = {i.filename for i in infos}
    content_types = zf.read("[Content_Types].xml").decode(errors="replace")
    if "word/vbaProject.bin" in names or "macroEnabled" in content_types:
        raise RejectedFile("MACRO_DOCUMENT", "documents with macros are not accepted")
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise RejectedFile("CORRUPT_FILE", "the document could not be read") from exc

    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(dict.fromkeys(cells)))
    text = "\n".join(lines)

    images: list[Image.Image] = []
    for name in sorted(n for n in names if n.startswith("word/media/")):
        if len(images) >= MAX_PAGES - 1:
            break
        try:
            img = Image.open(io.BytesIO(zf.read(name)))
            img.load()
            if min(img.size) >= 100:  # skip logos and icons
                images.append(ImageOps.exif_transpose(img).convert("RGB"))
        except Exception:  # noqa: BLE001, S112 - EMF/WMF and odd formats are skipped
            continue

    pages = ([_render_text(text)] if text else []) + images
    texts = [text] + [""] * len(images) if text else [""] * len(images)
    if not pages:
        raise RejectedFile("UNREADABLE_DOCUMENT", "the document has no text or images to read")
    cp = doc.core_properties
    props = {
        "author": cp.author,
        "last_modified_by": cp.last_modified_by,
        "created": cp.created.isoformat() if cp.created else None,
        "modified": cp.modified.isoformat() if cp.modified else None,
        "revision": cp.revision,
    }
    if "docProps/app.xml" in names:
        app_xml = zf.read("docProps/app.xml").decode(errors="replace")
        start = app_xml.find("<Application>")
        if start >= 0:
            props["application"] = app_xml[start + 13 : app_xml.find("</Application>")][:100]
    meta = {"docx": {k: v for k, v in props.items() if v}, "embedded_images": len(images)}
    return pages, texts, meta


def _read_eml(data: bytes, max_bytes: int) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    """A forwarded email: its body as text, plus every attachment read like an upload."""
    msg = email.message_from_bytes(data, policy=email.policy.default)
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        try:
            body = body_part.get_content()
        except (LookupError, ValueError):
            body = ""
        if body_part.get_content_type() == "text/html":
            body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
            body = re.sub(r"<br\s*/?>|</p>|</tr>|</div>", "\n", body, flags=re.I)
            body = re.sub(r"<[^>]+>", " ", body)
    body = "\n".join(" ".join(line.split()) for line in body.splitlines() if line.strip())
    header_text = "\n".join(f"{h}: {msg.get(h)}" for h in ("From", "Date", "Subject") if msg.get(h))
    pages: list[Image.Image] = []
    texts: list[str] = []
    if body:
        text = f"{header_text}\n{body}"[:MAX_TEXT_CHARS]
        pages.append(_render_text(text))
        texts.append(text)
    attachments = []
    for part in msg.iter_attachments():
        if len(pages) >= MAX_PAGES:
            break
        payload = part.get_payload(decode=True)
        name = part.get_filename() or part.get_content_type()
        try:
            # an attached message/rfc822 decodes to a Message, not bytes
            if not isinstance(payload, bytes) or sniff(payload) == EML:
                raise RejectedFile("NESTED_EMAIL", "nested emails are not unpacked")
            sub = prepare(payload, max_bytes)
        except RejectedFile as exc:
            attachments.append({"name": name, "read": False, "reason": exc.code})
            continue
        attachments.append(
            {
                "name": name,
                "read": True,
                "type": sub.content_type,
                "pages": len(sub.pages),
                "sha256": sub.sha256,
            }
        )
        room = MAX_PAGES - len(pages)
        pages.extend(sub.pages[:room])
        texts.extend(sub.page_texts[:room])
    if not pages:
        raise RejectedFile("UNREADABLE_DOCUMENT", "the email has no text or readable attachments")
    meta = {
        "email": {
            "from": str(msg.get("From", ""))[:200],
            "date": str(msg.get("Date", ""))[:100],
            "subject": str(msg.get("Subject", ""))[:300],
            "dkim_signed": msg.get("DKIM-Signature") is not None,
            "attachments": attachments,
        }
    }
    return pages, texts, meta


def _render_text(text: str, width: int = 1240) -> Image.Image:
    """A readable page image of document text, for the readers and the reviewer's viewer."""
    try:
        font: ImageFont.ImageFont | ImageFont.FreeTypeFont = ImageFont.truetype(
            "DejaVuSans.ttf", 26
        )
    except OSError:
        font = ImageFont.load_default()
    wrapped: list[str] = []
    for line in text.splitlines()[:120]:
        while len(line) > 80:
            cut = line.rfind(" ", 0, 80)
            cut = cut if cut > 20 else 80
            wrapped.append(line[:cut])
            line = line[cut:].lstrip()
        wrapped.append(line)
    img = Image.new("RGB", (width, max(400, 60 + 38 * len(wrapped))), "white")
    d = ImageDraw.Draw(img)
    for n, line in enumerate(wrapped):
        d.text((40, 30 + 38 * n), line, fill="black", font=font)
    return img


def _stack(pages: list[Image.Image], width: int = 1000) -> tuple[Image.Image, list]:
    """Pages scaled to one width and stacked, with each page's position as fractions."""
    scaled = [p.resize((width, max(1, round(p.height * width / p.width)))) for p in pages]
    total = sum(p.height for p in scaled)
    out = Image.new("RGB", (width, total), "white")
    layout, y = [], 0
    for p in scaled:
        out.paste(p, (0, y))
        layout.append((y / total, p.height / total))
        y += p.height
    return out, layout


def _exif(img: Image.Image) -> dict[str, Any]:
    try:
        raw = img.getexif()
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for tag_id, value in raw.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if name in {
            "Software",
            "DateTime",
            "Make",
            "Model",
            "DateTimeOriginal",
            "ProcessingSoftware",
            "Artist",
            "ImageDescription",
            "HostComputer",
        }:
            out[name] = str(value)
    return out


# metadata keys editors and generators write into PNG/WEBP text chunks and XMP
_TEXT_KEYS = (
    "software",
    "comment",
    "description",
    "parameters",
    "prompt",
    "workflow",
    "creator",
    "author",
    "title",
    "xmp",
    "xml:com.adobe.xmp",
    "c2pa",
    "source",
)


def _image_text(img: Image.Image) -> dict[str, str]:
    out = {}
    for key, value in (img.info or {}).items():
        if not isinstance(key, str) or key.startswith("pops-"):  # pops-* = test fixtures
            continue
        if any(k in key.lower() for k in _TEXT_KEYS) and isinstance(value, (str, bytes)):
            text = value.decode(errors="replace") if isinstance(value, bytes) else value
            out[key] = text[:500]
    return out


def _jpeg_quality(img: Image.Image) -> int | None:
    """Rough JPEG quality from the luminance quantisation table (re-saved images change it)."""
    try:
        tables = img.quantization  # type: ignore[attr-defined]
    except AttributeError:
        return None
    if not tables or 0 not in tables:
        return None
    avg = sum(tables[0]) / len(tables[0])
    # libjpeg's standard table averages ~57.6 at quality 50; scale per the IJG formula
    scale = avg / 57.625 * 100
    quality = (200 - scale) / 2 if scale <= 100 else 5000 / scale
    return max(1, min(100, round(quality)))


# ---- camera RAW: read the full-size photo every RAW file carries inside it

_RAW_MAKERS = (
    b"NIKON",
    b"SONY",
    b"FUJIFILM",
    b"OLYMPUS",
    b"PENTAX",
    b"Panasonic",
    b"LEICA",
    b"Canon",
)


def _tiff_has_tag(data: bytes, wanted: int) -> bool:
    """Is `wanted` a tag in the first directory of a TIFF-style file? (DNG has tag 50706.)"""
    import struct

    try:
        order = "<" if data[:2] == b"II" else ">"
        offset = struct.unpack(order + "I", data[4:8])[0]
        count = struct.unpack(order + "H", data[offset : offset + 2])[0]
        for i in range(min(count, 200)):
            entry = data[offset + 2 + 12 * i : offset + 14 + 12 * i]
            if len(entry) == 12 and struct.unpack(order + "H", entry[:2])[0] == wanted:
                return True
    except struct.error:
        return False
    return False


def _is_raw(data: bytes) -> bool:
    if data[4:12] == b"ftypcrx ":  # Canon CR3
        return True
    if data[:15] == b"FUJIFILMCCD-RAW":
        return True
    if data[:4] in (b"IIRO", b"IIRS", b"IIU\x00"):  # Olympus ORF, Panasonic RW2
        return True
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        if data[8:10] == b"CR":  # Canon CR2
            return True
        if _tiff_has_tag(data, 50706):  # DNGVersion
            return True
        # Nikon NEF / Sony ARW and friends: a camera maker in the header of a large TIFF container
        if len(data) > 3_000_000 and any(m in data[:8192] for m in _RAW_MAKERS):
            return True
    return False


def _raw_photo(data: bytes) -> tuple[Image.Image, dict[str, Any]]:
    """The largest JPEG inside a RAW file (its preview). Raw sensor data is never decoded."""
    starts = [m.start() for m in re.finditer(rb"\xff\xd8\xff", data)][:60]
    best = None
    for pos in starts:
        try:
            img = Image.open(io.BytesIO(data[pos : pos + 262_144]))  # the header says the size
            size = img.size
        except Exception:  # noqa: BLE001, S112 - not a real JPEG, keep looking
            continue
        if best is None or size[0] * size[1] > best[0]:
            best = (size[0] * size[1], pos)
    if best is None or best[0] < 160 * 160:
        raise RejectedFile(
            "RAW_NO_PREVIEW",
            "this RAW file has no photo inside that we can read: export it as JPEG and send that",
        )
    img = Image.open(io.BytesIO(data[best[1] : best[1] + 40 * 1024 * 1024]))
    img.load()
    return img, {"raw": {"preview_px": list(img.size), "bytes": len(data)}}


# ---- everyday documents beyond Word: spreadsheets, slides, OpenDocument, e-books, RTF, HTML, SVG

_MAX_ROWS = 300  # per sheet / table
_MAX_SHEETS = 6


def _xml(data: bytes):
    """Parse untrusted XML with entities, DTDs and the network switched off."""
    from lxml import etree

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise RejectedFile("CORRUPT_FILE", "the document could not be read") from exc


def _local(el) -> str:
    return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def _safe_zip(data: bytes) -> tuple[zipfile.ZipFile, set[str]]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if len(infos) > 2000 or sum(i.file_size for i in infos) > 60 * 1024 * 1024:
        raise RejectedFile("CORRUPT_FILE", "the document is too large when unpacked")
    names = {i.filename for i in infos}
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise RejectedFile("MACRO_DOCUMENT", "documents with macros are not accepted")
    if "[Content_Types].xml" in names and "macroEnabled" in zf.read("[Content_Types].xml").decode(
        errors="replace"
    ):
        raise RejectedFile("MACRO_DOCUMENT", "documents with macros are not accepted")
    return zf, names


def _zip_images(
    zf: zipfile.ZipFile, names: set[str], prefixes: tuple[str, ...]
) -> list[Image.Image]:
    images: list[Image.Image] = []
    for name in sorted(n for n in names if n.startswith(prefixes)):
        if len(images) >= MAX_PAGES - 1:
            break
        try:
            img = Image.open(io.BytesIO(zf.read(name)))
            img.load()
            if min(img.size) >= 100:  # skip logos and icons
                images.append(ImageOps.exif_transpose(img).convert("RGB"))
        except Exception:  # noqa: BLE001, S112 - EMF/WMF and odd formats are skipped
            continue
    return images


def _core_props(zf: zipfile.ZipFile, names: set[str]) -> dict[str, Any]:
    """Who made and last saved an Office file, and when (docProps/core.xml)."""
    if "docProps/core.xml" not in names:
        return {}
    try:
        root = _xml(zf.read("docProps/core.xml"))
    except RejectedFile:
        return {}
    wanted = {
        "creator": "author",
        "lastModifiedBy": "last_modified_by",
        "created": "created",
        "modified": "modified",
    }
    out = {}
    for el in root.iter():
        name = _local(el)
        if name in wanted and el.text and el.text.strip():
            out[wanted[name]] = el.text.strip()[:100]
    return out


def _doc_result(
    text: str, images: list[Image.Image], meta: dict[str, Any], what: str
) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    text = text.strip()[:MAX_TEXT_KEPT]
    pages = ([_render_text(text)] if text else []) + images
    texts = ([text] if text else []) + [""] * len(images)
    if not pages:
        raise RejectedFile("UNREADABLE_DOCUMENT", f"the {what} has no text or images to read")
    meta["embedded_images"] = len(images)
    return pages, texts, meta


def _read_xlsx(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    zf, names = _safe_zip(data)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(zf.read("xl/sharedStrings.xml")):
            shared.append("".join(x.text or "" for x in si.iter() if _local(x) == "t"))
    lines: list[str] = []
    sheets = sorted(
        (n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
        key=lambda n: int(re.findall(r"\d+", n)[-1]),
    )
    for name in sheets[:_MAX_SHEETS]:
        rows = 0
        for row in _xml(zf.read(name)).iter():
            if _local(row) != "row":
                continue
            cells = []
            for c in row:
                if _local(c) != "c":
                    continue
                kind = c.get("t")
                val = ""
                for child in c:
                    if _local(child) == "v" and child.text is not None:
                        val = child.text
                    elif _local(child) == "is":
                        val = "".join(x.text or "" for x in child.iter() if _local(x) == "t")
                if kind == "s" and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
                if val.strip():
                    cells.append(val.strip())
            if cells:
                lines.append(" | ".join(cells))
                rows += 1
                if rows >= _MAX_ROWS:
                    break
    meta = {"office": {"format": "xlsx", "sheets": len(sheets), **_core_props(zf, names)}}
    return _doc_result(
        "\n".join(lines), _zip_images(zf, names, ("xl/media/",)), meta, "spreadsheet"
    )


def _read_pptx(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    zf, names = _safe_zip(data)
    slides = sorted(
        (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.findall(r"\d+", n)[-1]),
    )
    lines: list[str] = []
    for name in slides[: MAX_PAGES * 3]:
        parts = [
            x.text.strip()
            for x in _xml(zf.read(name)).iter()
            if _local(x) == "t" and x.text and x.text.strip()
        ]
        if parts:
            lines.append(" | ".join(parts))
    meta = {"office": {"format": "pptx", "slides": len(slides), **_core_props(zf, names)}}
    return _doc_result(
        "\n".join(lines), _zip_images(zf, names, ("ppt/media/",)), meta, "presentation"
    )


def _odf_lines(root) -> list[str]:
    lines: list[str] = []
    for el in root.iter():
        name = _local(el)
        if name in ("p", "h") and not any(_local(a) == "table-cell" for a in el.iterancestors()):
            line = " ".join("".join(el.itertext()).split())
            if line:
                lines.append(line)
        elif name == "table-row":
            cells = [
                " ".join("".join(c.itertext()).split()) for c in el if _local(c) == "table-cell"
            ]
            cells = [c for c in cells if c]
            if cells:
                lines.append(" | ".join(cells))
    return lines[: _MAX_ROWS * _MAX_SHEETS]


def _read_odf(data: bytes, fmt: str) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    zf, names = _safe_zip(data)
    if "content.xml" not in names:
        raise RejectedFile("CORRUPT_FILE", "the document could not be read")
    lines = _odf_lines(_xml(zf.read("content.xml")))
    meta: dict[str, Any] = {"office": {"format": fmt}}
    if "meta.xml" in names:
        try:
            for el in _xml(zf.read("meta.xml")).iter():
                key = {
                    "initial-creator": "author",
                    "creator": "last_modified_by",
                    "creation-date": "created",
                    "date": "modified",
                }.get(_local(el))
                if key and el.text:
                    meta["office"][key] = el.text.strip()[:100]
        except RejectedFile:
            pass
    return _doc_result("\n".join(lines), _zip_images(zf, names, ("Pictures/",)), meta, "document")


class _TextOf(html.parser.HTMLParser):
    """Visible text of an HTML page. Scripts, styles and comments are dropped; nothing is run."""

    BLOCK = {
        "p",
        "div",
        "br",
        "tr",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "section",
        "article",
        "td",
        "th",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template", "head"):
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.out.append("\n" if tag != "td" and tag != "th" else " | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "head") and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.out.append(data)


def _html_text(raw: str) -> tuple[str, str]:
    parser = _TextOf()
    parser.feed(raw[:2_000_000])
    parser.close()
    text = "\n".join(" ".join(line.split()) for line in "".join(parser.out).splitlines())
    text = "\n".join(line for line in text.splitlines() if line.strip(" |"))
    return text, " ".join(parser.title.split())[:200]


def _read_html(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    text, title = _html_text(data.decode("utf-8", errors="replace"))
    meta = {"office": {"format": "html", **({"title": title} if title else {})}}
    return _doc_result(text, [], meta, "web page")


def _read_epub(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    zf, names = _safe_zip(data)
    chapters = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
    parts = []
    for name in chapters[:30]:
        text, _ = _html_text(zf.read(name).decode("utf-8", errors="replace"))
        if text:
            parts.append(text)
        if sum(map(len, parts)) > MAX_TEXT_KEPT:
            break
    meta = {"office": {"format": "epub", "chapters": len(chapters)}}
    return _doc_result("\n\n".join(parts), [], meta, "e-book")


_RTF_SKIP = {
    "fonttbl",
    "colortbl",
    "stylesheet",
    "info",
    "pict",
    "header",
    "footer",
    "themedata",
    "colorschememapping",
    "datastore",
    "latentstyles",
    "listtable",
    "listoverridetable",
    "rsidtbl",
    "generator",
}


def _rtf_text(raw: str) -> str:
    """Plain text of an RTF file, by walking its groups. Hidden parts and pictures are skipped."""
    out: list[str] = []
    skip_depth: list[bool] = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "{":
            nxt = raw[i + 1 : i + 40]
            m = re.match(r"\\\*|\\([a-z]+)", nxt)
            hidden = bool(m and (m.group(0) == "\\*" or m.group(1) in _RTF_SKIP))
            skip_depth.append(hidden or (bool(skip_depth) and skip_depth[-1]))
            i += 1
        elif ch == "}":
            if skip_depth:
                skip_depth.pop()
            i += 1
        elif ch == "\\":
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?", raw[i:])
            if m:
                word = m.group(1)
                if not (skip_depth and skip_depth[-1]):
                    if word in ("par", "line", "row", "sect"):
                        out.append("\n")
                    elif word == "tab" or word == "cell":
                        out.append(" | " if word == "cell" else "\t")
                i += m.end()
            elif raw[i + 1 : i + 2] == "'" and re.match(r"[0-9a-fA-F]{2}", raw[i + 2 : i + 4]):
                if not (skip_depth and skip_depth[-1]):
                    out.append(
                        bytes([int(raw[i + 2 : i + 4], 16)]).decode("cp1252", errors="replace")
                    )
                i += 4
            else:
                if raw[i + 1 : i + 2] in ("\\", "{", "}") and not (skip_depth and skip_depth[-1]):
                    out.append(raw[i + 1])
                i += 2
        else:
            if not (skip_depth and skip_depth[-1]) and ch not in "\r\n":
                out.append(ch)
            i += 1
    text = "".join(out)
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _read_rtf(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    return _doc_result(
        _rtf_text(data.decode("latin-1")), [], {"office": {"format": "rtf"}}, "document"
    )


def _render_svg(data: bytes) -> tuple[list[Image.Image], list[str], dict[str, Any]]:
    """An SVG drawn to pixels by MuPDF. It runs no scripts and fetches nothing."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="svg")
        page = doc.load_page(0)
        longest = max(page.rect.width, page.rect.height, 1)
        zoom = min(4.0, 2000 / longest)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        text = page.get_text().strip()
    except Exception as exc:  # noqa: BLE001
        raise RejectedFile("CORRUPT_FILE", "the SVG could not be drawn") from exc
    return [img], [text], {"svg": {"has_text": bool(text)}}


def _frames(img: Image.Image) -> list[Image.Image]:
    """Every page of a TIFF scan (up to MAX_PAGES), or the first frame of a GIF."""
    n = getattr(img, "n_frames", 1)
    if img.format != "TIFF" or n <= 1:
        return [img]
    out = []
    for frame in ImageSequence.Iterator(img):
        out.append(frame.copy())
        if len(out) >= MAX_PAGES:
            break
    return out


def _qr_codes(pages: list[Image.Image]) -> list[str]:
    """Text of any QR codes on the first pages (receipts often carry a verification link or
    reference). It is shown to a reviewer as data only: nothing is opened or fetched."""
    import cv2
    import numpy as np

    found: list[str] = []
    detector = cv2.QRCodeDetector()
    for page in pages[:3]:
        try:
            gray = cv2.cvtColor(np.array(page), cv2.COLOR_RGB2GRAY)
            if max(gray.shape) > 2400:  # keep the search quick on very large scans
                k = 2400 / max(gray.shape)
                gray = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            value, _, _ = detector.detectAndDecode(gray)
        except Exception:  # noqa: BLE001, S112 - a QR that cannot be read is simply not reported
            continue
        text = (value or "").strip()
        if text and text not in found:
            found.append(text[:500])
    return found[:5]


def prepare(data: bytes, max_bytes: int, raw_max_bytes: int | None = None) -> PreparedFile:
    """Validate and read one file. `raw_max_bytes` lets camera RAW (large by nature) exceed
    `max_bytes`; nothing else may."""
    if len(data) == 0:
        raise RejectedFile("EMPTY_FILE", "the file is empty")
    if len(data) > max_bytes:
        too_big_for_raw = raw_max_bytes is None or len(data) > raw_max_bytes
        if too_big_for_raw or not _is_raw(data):
            raise RejectedFile("TOO_LARGE", f"files must be under {max_bytes // (1024 * 1024)} MB")
    ctype = sniff(data)
    sha = hashlib.sha256(data).hexdigest()
    meta: dict[str, Any] = {}
    texts: list[str] = []
    if ctype == "application/pdf":
        pages, texts, meta = _render_pdf(data)
    elif ctype == DOCX:
        pages, texts, meta = _read_docx(data)
    elif ctype == XLSX:
        pages, texts, meta = _read_xlsx(data)
    elif ctype == PPTX:
        pages, texts, meta = _read_pptx(data)
    elif ctype in (ODT, ODS, ODP):
        pages, texts, meta = _read_odf(data, {ODT: "odt", ODS: "ods", ODP: "odp"}[ctype])
    elif ctype == EPUB:
        pages, texts, meta = _read_epub(data)
    elif ctype == RTF:
        pages, texts, meta = _read_rtf(data)
    elif ctype == HTML:
        pages, texts, meta = _read_html(data)
    elif ctype == SVG:
        pages, texts, meta = _render_svg(data)
    elif ctype == TEXT:
        text = data.decode("utf-8-sig").strip()
        pages, texts, meta = [_render_text(text)], [text], {"pasted_text": {"chars": len(text)}}
    elif ctype == EML:
        pages, texts, meta = _read_eml(data, max_bytes)
    else:
        try:
            if ctype == RAW:
                img, raw_meta = _raw_photo(data)
                meta.update(raw_meta)
            else:
                img = Image.open(io.BytesIO(data))
                img.load()
        except RejectedFile:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RejectedFile("CORRUPT_FILE", "the image could not be decoded") from exc
        exif = _exif(img)
        if exif:
            meta["exif"] = exif  # a hint only: screenshots wipe EXIF, editors leave traces
        text_chunks = _image_text(img)
        if text_chunks:
            meta["image_text"] = text_chunks
        if ctype == "image/jpeg":
            meta["jpeg_quality"] = _jpeg_quality(img)
        frames = _frames(img)
        if ctype == "image/gif" and getattr(img, "is_animated", False):
            meta["animated_frames"] = getattr(
                img, "n_frames", 1
            )  # a still is read: the first frame
        pages = [ImageOps.exif_transpose(f).convert("RGB") for f in frames]
    first = pages[0]
    qr = _qr_codes(pages) if ctype not in RENDERED_TYPES else []
    if qr:
        meta["qr"] = qr
    meta["width"], meta["height"] = first.size
    meta["pages"] = len(pages)
    if len(pages) > 1:
        preview, layout = _stack(pages)
    else:
        preview, layout = first, [(0.0, 1.0)]
    buf = io.BytesIO()
    preview.save(buf, format="PNG")
    return PreparedFile(
        content_type=ctype,
        sha256=sha,
        image=first,
        phash=str(imagehash.phash(first)),
        meta=meta,
        preview_png=buf.getvalue(),
        pages=pages,
        page_texts=texts or [""] * len(pages),
        page_layout=layout,
    )


def phash_distance(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def phash_to_int(hex_hash: str) -> int:
    """64-bit perceptual hash as a signed BIGINT (same bits as Postgres ('x'||hex)::bit(64))."""
    n = int(hex_hash, 16)
    return n - (1 << 64) if n >= 1 << 63 else n
