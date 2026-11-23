#!/usr/bin/env python3
"""Index an EPUB into a SQLite FTS5 database, paragraph by paragraph.

What it does
    Reads the EPUB (a zip of XHTML) in spine order, splits every file into
    paragraphs and stores them in SQLite with full-text search. The EPUB is
    never extracted to disk and never modified.

Decisions embedded
    - Standard library only: an EPUB is plain XHTML, so no layout analysis
      or OCR (Docling) is needed.
    - Each paragraph keeps its section (file code, e.g. c05, nota), its kind
      (text | notes | bibliography | index | front) and the printed page
      number taken from the `<a id="page_NNN">` anchors, so a hit can be
      cited as "p. 382".
    - Kind is guessed from the file name used by this publisher's export
      (c01..c09, pro, epi = text; nota/notb = notes; bib; ind). For another
      EPUB adjust KIND_BY_CODE.
    - Notes are the interesting part for source checking: Dash cites
      archive material there (ARA, JFP, DB, letters).

Usage
    python scripts/build_epub_index.py "corpus/Batavia's Graveyard - Mike Dash.epub"
    python scripts/build_epub_index.py BOOK.epub --db build/dash.sqlite

Output
    SQLite database (default build/dash.sqlite) with table `passages`
    (id, section, kind, seq, page, text) and FTS5 table `passages_fts`.
    Query it with scripts/search_epub.py. Throw-away: re-run to rebuild.
"""

import argparse
import re
import sqlite3
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from posixpath import dirname, join
from xml.etree import ElementTree as ET

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote"}
CELL_TAGS = {"td", "th"}
SKIP_TAGS = {"script", "style", "head"}
PAGE_ID = re.compile(r"^page_(\d+)$")

KIND_BY_CODE = {
    **{f"c{n:02d}": "text" for n in range(1, 30)},
    "pro": "text", "epi": "text", "pre": "text",
    "nota": "notes", "notb": "notes",
    "bib": "bibliography", "ind": "index",
}
NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "o": "http://www.idpf.org/2007/opf",
}


class ParagraphParser(HTMLParser):
    """Collect (page, text) paragraphs from one XHTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[tuple[int | None, str]] = []
        self.page: int | None = None
        self._buf: list[str] = []
        self._skip = 0
        self._para_page: int | None = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in CELL_TAGS:
            self._buf.append(" | ")
        if tag == "a":
            m = PAGE_ID.match(dict(attrs).get("id") or "")
            if m:
                self.page = int(m.group(1))

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        if not self._buf:
            self._para_page = self.page
        self._buf.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip(" |")
        self._buf = []
        if text:
            self.paragraphs.append((self._para_page, text))


def spine_files(zf: zipfile.ZipFile) -> list[str]:
    """Return the XHTML member names in reading order."""
    container = ET.fromstring(zf.read("META-INF/container.xml"))
    opf_path = container.find(".//c:rootfile", NS).attrib["full-path"]
    opf = ET.fromstring(zf.read(opf_path))
    manifest = {i.attrib["id"]: i.attrib["href"] for i in opf.findall(".//o:item", NS)}
    base = dirname(opf_path)
    return [join(base, manifest[r.attrib["idref"]]) for r in opf.findall(".//o:itemref", NS)]


def section_code(member: str) -> str:
    """'OEBPS/9781780220581_oeb_c05_r1.html' -> 'c05'."""
    m = re.search(r"_oeb_(.+?)_r\d+\.x?html?$", member)
    return m.group(1) if m else Path(member).stem


def build(epub: Path, db: Path) -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE passages (
            id INTEGER PRIMARY KEY, section TEXT, kind TEXT,
            seq INTEGER, page INTEGER, text TEXT);
        CREATE VIRTUAL TABLE passages_fts USING fts5(
            text, content='passages', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2');
        """
    )
    n = 0
    with zipfile.ZipFile(epub) as zf:
        for member in spine_files(zf):
            code = section_code(member)
            parser = ParagraphParser()
            parser.feed(zf.read(member).decode("utf-8-sig"))
            kind = KIND_BY_CODE.get(code, "front")
            last_page = None
            for seq, (page, text) in enumerate(parser.paragraphs):
                page = page or last_page  # carry page forward within a section
                last_page = page
                con.execute(
                    "INSERT INTO passages(section, kind, seq, page, text) VALUES (?,?,?,?,?)",
                    (code, kind, seq, page, text),
                )
                n += 1
    con.execute("INSERT INTO passages_fts(passages_fts) VALUES ('rebuild')")
    con.commit()
    con.close()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Index an EPUB into SQLite FTS5.")
    ap.add_argument("epub", type=Path)
    ap.add_argument("--db", type=Path, default=Path("build/dash.sqlite"),
                    help="output database (default: build/dash.sqlite)")
    args = ap.parse_args()
    n = build(args.epub, args.db)
    print(f"indexed {n} passages into {args.db}")


if __name__ == "__main__":
    main()
