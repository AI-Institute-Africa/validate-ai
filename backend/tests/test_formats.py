"""Every everyday document and image type is read, safely, or refused with advice."""

import io
import zipfile

import pytest
from PIL import Image

from app.intake import files
from app.intake.files import RejectedFile, prepare, sniff
from tests.conftest import login
from tests.test_flow import TXN, _obligation

MAX = 10 * 1024 * 1024
CORE = (
    "<cp:coreProperties xmlns:cp='x' xmlns:dc='y'>"
    "<dc:creator>Tendai</dc:creator></cp:coreProperties>"
)
LINES = ["EcoCash", "Payment Successful", f"Txn ID: {TXN}", "Amount: USD 40.00"]


def _img(fmt: str, size=(400, 300), **kw) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format=fmt, **kw)
    return buf.getvalue()


def _zip(parts: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in parts.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _xlsx() -> bytes:
    rows = "".join(
        f'<row r="{i}"><c r="A{i}" t="s"><v>{i - 1}</v></c><c r="B{i}"><v>{i * 10}</v></c></row>'
        for i in range(1, 5)
    )
    strings = "".join(f"<si><t>{line}</t></si>" for line in LINES)
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": "<workbook/>",
            "xl/sharedStrings.xml": f"<sst>{strings}</sst>",
            "xl/worksheets/sheet1.xml": f"<worksheet><sheetData>{rows}</sheetData></worksheet>",
            "docProps/core.xml": CORE,
        }
    )


def _pptx() -> bytes:
    body = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in LINES)
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "ppt/presentation.xml": "<presentation/>",
            "ppt/slides/slide1.xml": f"<p:sld xmlns:a='a' xmlns:p='p'>{body}</p:sld>",
        }
    )


def _odf(kind: str) -> bytes:
    cell = (
        "<table:table-row><table:table-cell><text:p>{}</text:p>"
        "</table:table-cell></table:table-row>"
    )
    rows = "".join(cell.format(line) for line in LINES)
    ns = "xmlns:office='o' xmlns:table='t' xmlns:text='x'"
    return _zip(
        {
            "mimetype": f"application/vnd.oasis.opendocument.{kind}",
            "content.xml": f"<office:document-content {ns}>{rows}</office:document-content>",
        }
    )


EPUB = _zip(
    {
        "mimetype": "application/epub+zip",
        "OEBPS/ch1.xhtml": "<html><body><p>" + "</p><p>".join(LINES) + "</p></body></html>",
    }
)
HTML = (
    "<!doctype html><html><head><title>Receipt</title><script>alert(1)</script></head><body>"
    + "".join(f"<p>{x}</p>" for x in LINES)
    + "</body></html>"
).encode()
RTF = ("{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}\\f0 " + "\\par ".join(LINES) + "}").encode()
SVG = (
    '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
    '<text x="10" y="40" font-size="20">Txn ID: ' + TXN + "</text></svg>"
).encode()


@pytest.mark.parametrize(
    ("name", "data", "ctype"),
    [
        ("gif", _img("GIF"), "image/gif"),
        ("bmp", _img("BMP"), "image/bmp"),
        ("tiff", _img("TIFF"), "image/tiff"),
        ("avif", _img("AVIF"), "image/avif"),
        ("xlsx", _xlsx(), files.XLSX),
        ("pptx", _pptx(), files.PPTX),
        ("ods", _odf("spreadsheet"), files.ODS),
        ("odt", _odf("text"), files.ODT),
        ("odp", _odf("presentation"), files.ODP),
        ("epub", EPUB, files.EPUB),
        ("html", HTML, files.HTML),
        ("rtf", RTF, files.RTF),
        ("svg", SVG, files.SVG),
    ],
)
def test_each_type_is_recognised_and_read(name, data, ctype):
    assert sniff(data) == ctype, name
    p = prepare(data, MAX)
    assert p.content_type == ctype and p.pages and p.preview_png.startswith(b"\x89PNG")


@pytest.mark.parametrize("name", ["xlsx", "pptx", "ods", "odt", "odp", "epub", "html", "rtf"])
def test_the_words_are_read_out_of_text_documents(name):
    data = {
        "xlsx": _xlsx(),
        "pptx": _pptx(),
        "ods": _odf("spreadsheet"),
        "odt": _odf("text"),
        "odp": _odf("presentation"),
        "epub": EPUB,
        "html": HTML,
        "rtf": RTF,
    }[name]
    text = prepare(data, MAX).text
    assert "Payment Successful" in text or "Txn ID" in text, (name, text[:200])
    assert "alert(1)" not in text  # a script in a web page is never text we read


def test_spreadsheet_numbers_and_authorship_are_kept():
    p = prepare(_xlsx(), MAX)
    assert "20" in p.text and p.meta["office"]["format"] == "xlsx"
    assert p.meta["office"]["author"] == "Tendai"


def test_a_multi_page_tiff_scan_gives_every_page():
    buf = io.BytesIO()
    pages = [Image.new("RGB", (300, 300), c) for c in ("white", "lightgray", "gray")]
    pages[0].save(buf, format="TIFF", save_all=True, append_images=pages[1:])
    p = prepare(buf.getvalue(), MAX)
    assert len(p.pages) == 3 and p.meta["pages"] == 3


def test_an_animated_gif_reads_its_first_frame_and_says_so():
    buf = io.BytesIO()
    frames = [Image.new("RGB", (120, 120), c) for c in ("red", "blue")]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    p = prepare(buf.getvalue(), MAX)
    assert len(p.pages) == 1 and p.meta["animated_frames"] == 2


def test_old_binary_office_files_are_refused_with_advice():
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600
    with pytest.raises(RejectedFile) as e:
        prepare(ole, MAX)
    assert e.value.code == "LEGACY_OFFICE" and "PDF" in str(e.value)


def test_macros_are_refused_in_every_office_format():
    macro = _zip(
        {"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<w/>", "xl/vbaProject.bin": b"x"}
    )
    with pytest.raises(RejectedFile) as e:
        prepare(macro, MAX)
    assert e.value.code == "MACRO_DOCUMENT"


def test_an_unpacked_size_bomb_is_refused():
    bomb = _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": "<w/>",
            "xl/big.bin": b"\0" * (61 * 1024 * 1024),
        }
    )
    with pytest.raises(RejectedFile) as e:
        prepare(bomb, 100 * 1024 * 1024)
    assert e.value.code == "CORRUPT_FILE"


def test_xml_entities_are_not_expanded():
    evil = (
        '<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a "AAAAAAAAAA">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">'
        '<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;">]><sst><si><t>&c;</t></si></sst>'
    )
    data = _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": "<w/>",
            "xl/sharedStrings.xml": evil,
            "xl/worksheets/sheet1.xml": (
                "<worksheet><sheetData><row><c t='s'><v>0</v></c></row></sheetData></worksheet>"
            ),
        }
    )
    try:
        text = prepare(data, MAX).text
    except RejectedFile:
        return  # refusing it is also fine
    assert "AAAAAAAAAA" not in text


def test_still_refused_types_say_what_is_accepted():
    for junk in (
        b"MZ\x90\x00" + b"\x00" * 100,
        b"\x1f\x8b\x08" + b"\x00" * 60,
        b"RIFF....WAVE" + b"\x00" * 40,
    ):
        with pytest.raises(RejectedFile) as e:
            prepare(junk, MAX)
        assert e.value.code in ("UNSUPPORTED_TYPE", "CORRUPT_FILE")
    with pytest.raises(RejectedFile) as e:
        prepare(b"MZ\x90\x00" + b"\x00" * 100, MAX)
    assert "TIFF" in str(e.value) and "Excel" in str(e.value)


def test_a_spreadsheet_proof_goes_through_the_whole_pipeline_and_is_flagged_as_editable(client):
    h, rev = login(client, "submitter"), login(client, "reviewer")
    ob = _obligation(client, h)
    r = client.post(
        "/claims",
        headers=h,
        data={
            "obligation_id": ob["obligation_id"],
            "claimant_ref": "learner-1",
            "channel": "ecocash",
        },
        files={"file": ("proof.xlsx", _xlsx(), files.XLSX)},
    )
    assert r.status_code == 201, r.text
    detail = client.get(f"/review/claims/{r.json()['claim_id']}", headers=rev).json()
    assert detail["evidence"][0]["content_type"] == files.XLSX
    codes = {s["code"] for s in detail["claim"]["risk_signals"]}
    assert "EDITABLE_DOCUMENT" in codes


def test_web_and_vector_originals_are_only_ever_downloaded(client):
    h, rev = login(client, "submitter"), login(client, "reviewer")
    ob = _obligation(client, h)
    for name, data, ctype in (("p.html", HTML, "text/html"), ("p.svg", SVG, "image/svg+xml")):
        r = client.post(
            "/claims",
            headers=h,
            data={
                "obligation_id": ob["obligation_id"],
                "claimant_ref": "learner-1",
                "channel": "ecocash",
            },
            files={"file": (name, data, ctype)},
        )
        assert r.status_code == 201, r.text
        ev = client.get(f"/review/claims/{r.json()['claim_id']}", headers=rev).json()["evidence"][0]
        got = client.get(ev["original_url"])
        assert got.headers["content-type"].startswith("application/octet-stream")
        assert "attachment" in got.headers["content-disposition"]
        assert got.headers["x-content-type-options"] == "nosniff"
