#!/usr/bin/env python3
"""Convert Transkribus PAGE-XML files to plain text, one text file per page.

What it does
    Reads PAGE-XML (2013-07-15 schema) and writes the line-level transcription
    (TextLine/TextEquiv, not the duplicated Word/TextEquiv) in reading order,
    one line per text line, plus a combined file with page markers.

Decisions embedded
    - Inputs are read-only; output goes to build/ and is throw-away.
    - Reading order follows the `readingOrder {index:N;}` in `custom`;
      falls back to document order when it is missing.
    - Page number is taken from the file name (..._4994_0003-groot.xml -> 3),
      which matches the scan numbers of the archief MCP (list_scans).
    - The model/version that produced the HTR is read from <Creator> and
      written to the header, because the same inventory can have pages from
      different model versions (see 4994 scan 5).
    - No text normalisation: HTR errors are kept as they are.

Usage
    python scripts/pagexml_to_text.py NL-HaNA_1.04.02_4994_00*-groot.xml
    python scripts/pagexml_to_text.py FILES... --outdir build/4994

Output
    <outdir>/page_NNNN.txt   one transcription line per line
    <outdir>/all.txt         all pages, '=== scan N (creator) ===' headers
"""

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"}
ORDER = re.compile(r"readingOrder\s*\{\s*index:\s*(\d+)")


def reading_index(elem: ET.Element, fallback: int) -> int:
    m = ORDER.search(elem.get("custom", ""))
    return int(m.group(1)) if m else fallback


def page_lines(path: Path) -> tuple[str, list[str]]:
    """Return (creator, lines) for one PAGE-XML file."""
    root = ET.parse(path).getroot()
    creator = (root.findtext("p:Metadata/p:Creator", default="?", namespaces=NS) or "?").strip()
    lines: list[str] = []
    regions = root.findall(".//p:TextRegion", NS)
    regions.sort(key=lambda r: reading_index(r, 10**6))
    for region in regions:
        tls = region.findall("p:TextLine", NS)
        tls.sort(key=lambda t: reading_index(t, 10**6))
        for tl in tls:
            text = tl.findtext("p:TextEquiv/p:Unicode", default="", namespaces=NS)
            if text.strip():
                lines.append(text.strip())
    return creator, lines


def scan_number(path: Path) -> int:
    m = re.search(r"_(\d{4})(?:-[a-z]+)?\.xml$", path.name)
    return int(m.group(1)) if m else 0


def short_creator(creator: str) -> str:
    m = re.search(r"name=([^:]+):version=([^:]+):model_id=(\d+)", creator)
    return f"{m.group(1)} {m.group(2)} model {m.group(3)}" if m else creator


def main() -> None:
    ap = argparse.ArgumentParser(description="PAGE-XML -> plain text per page.")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("build/4994"))
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    combined: list[str] = []
    for path in sorted(args.files, key=scan_number):
        creator, lines = page_lines(path)
        n = scan_number(path)
        (args.outdir / f"page_{n:04d}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        combined.append(f"=== scan {n} ({short_creator(creator)}) — {len(lines)} lines ===")
        combined.extend(lines)
        combined.append("")
        print(f"scan {n}: {len(lines)} lines, {short_creator(creator)}")
    (args.outdir / "all.txt").write_text("\n".join(combined), encoding="utf-8")
    print(f"wrote {args.outdir}/all.txt")


if __name__ == "__main__":
    main()
