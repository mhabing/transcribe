"""Extract plain text from PDFs via an Apache Tika server (with OCR fallback).

Decisions embedded:
  - Source PDFs are read-only; output goes to build/text/<stem>.txt (throw-away).
  - Strategy 'ocr_only' is used because the target PDFs are image-only scans;
    use --strategy auto for PDFs that may have a text layer.
  - Existing outputs are skipped unless --force (re-runnable from scratch).
  - OCR quality on old typescripts is imperfect: treat hits as indications.

Usage:
  uv run scripts/tika_extract.py corpus/no._081_beacon_island.pdf corpus/no._003_batavia_exc.pdf
  uv run scripts/tika_extract.py --strategy auto --force corpus/*.pdf

Config (.env or environment):
  TIKA_URL   base URL of the Tika server, default http://192.168.1.29:9998

Output: one UTF-8 text file per PDF in --out-dir (default build/text).
"""
import argparse
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


def extract(pdf: Path, tika_url: str, strategy: str, lang: str, timeout: int) -> str:
    """PUT the PDF to Tika's /tika endpoint and return the extracted text."""
    req = urllib.request.Request(
        f"{tika_url}/tika",
        data=pdf.read_bytes(),
        method="PUT",
        headers={
            "Accept": "text/plain",
            "X-Tika-PDFOcrStrategy": strategy,
            "X-Tika-OCRLanguage": lang,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("pdfs", nargs="+", type=Path)
    p.add_argument("--tika-url", default=os.getenv("TIKA_URL", "http://192.168.1.29:9998"))
    p.add_argument("--out-dir", type=Path, default=Path("build/text"))
    p.add_argument("--strategy", default="ocr_only",
                   choices=["auto", "ocr_only", "no_ocr", "ocr_and_text_extraction"])
    p.add_argument("--lang", default="eng+nld")
    p.add_argument("--timeout", type=int, default=3600, help="seconds per file")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for pdf in args.pdfs:
        out = args.out_dir / f"{pdf.stem}.txt"
        if out.exists() and not args.force:
            print(f"skip  {out} (exists)")
            continue
        print(f"tika  {pdf} ...", flush=True)
        try:
            out.write_text(extract(pdf, args.tika_url, args.strategy, args.lang, args.timeout))
            print(f"ok    {out} ({out.stat().st_size} bytes)", flush=True)
        except Exception as e:  # keep going; report at the end
            print(f"FAIL  {pdf}: {e}", file=sys.stderr, flush=True)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
