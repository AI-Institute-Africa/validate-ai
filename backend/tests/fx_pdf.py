"""Build a PDF that reproduces the RBZ daily rates table (the layout seen on 13 November 2026)."""

import pymupdf


def rbz_pdf(
    date_line: str = "Friday, 13 November 2026",
    usd: tuple[str, str, str, str, str, str] = (
        "1",
        "1",
        "1.0000",
        "25.9214",
        "27.2508",
        "26.5861",
    ),
    *,
    headings: bool = True,
    interbank: bool = True,
    extra_row_first: bool = False,
) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)

    def put(x: float, y: float, text: str) -> None:
        page.insert_text((x, y), text, fontsize=9)

    put(330, 50, date_line)
    if headings:
        for x, t in [
            (30, "CURRENCY"),
            (130, "INDICES"),
            (240, "BID"),
            (320, "ASK"),
            (385, "MID RATE"),
            (470, "BID RATE"),
            (550, "ASK RATE"),
            (640, "MID RATE"),
        ]:
            put(x, 90, t)
        for x in (480, 560, 650):
            put(x, 104, "ZWG")
    if interbank:
        put(30, 125, "INTERBANK RATE")
    if extra_row_first:
        put(60, 140, "EUR")
    y = 150
    put(60, y, "USD")
    for x, t in zip((250, 325, 395, 495, 575, 665), usd, strict=True):
        put(x, y, t)
    data = doc.tobytes()
    doc.close()
    return data
