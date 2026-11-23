#!/usr/bin/env python3
"""Full-text search in the SQLite index built by build_epub_index.py.

What it does
    Runs an FTS5 query and prints matching paragraphs with section, kind and
    printed page number, plus a highlighted snippet.

Decisions embedded
    - Default query mode is FTS5 syntax (OR, NEAR, prefix*, "phrases").
    - Searching is restricted with --kind (text, notes, bibliography, index).
    - Dash cites archive material with old numbering (ARA, "VOC 1098",
      JFP = Pelsaert's journal, DB = Drake-Brockman page). Use --refs to list
      only the notes that look like archive citations.

Usage
    python scripts/search_epub.py "sardam"
    python scripts/search_epub.py "NEAR(verdict Jeronimus, 5)" --kind notes
    python scripts/search_epub.py --refs --limit 200
    python scripts/search_epub.py "ARA" --db build/dash.sqlite --context 1

Output
    One block per hit: [kind section p.PAGE #seq] snippet (or full text with
    --full).
"""

import argparse
import re
import sqlite3
from pathlib import Path

REF_PATTERN = re.compile(r"\b(ARA|VOC\s*\d+|JFP|DB\s*\d+|GAA|GAD|GAH|GAL|letter of|Resolution)\b")


def search(con: sqlite3.Connection, query: str, kind: str | None, limit: int):
    sql = (
        "SELECT p.id, p.kind, p.section, p.page, p.seq, "
        "snippet(passages_fts, 0, '«', '»', ' … ', 24), p.text "
        "FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid "
        "WHERE passages_fts MATCH ?"
    )
    params: list = [query]
    if kind:
        sql += " AND p.kind = ?"
        params.append(kind)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return con.execute(sql, params).fetchall()


def refs(con: sqlite3.Connection, limit: int):
    rows = con.execute(
        "SELECT id, kind, section, page, seq, text, text FROM passages "
        "WHERE kind IN ('notes', 'bibliography') ORDER BY id"
    ).fetchall()
    return [r for r in rows if REF_PATTERN.search(r[5])][:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="Search the EPUB index.")
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("--db", type=Path, default=Path("build/dash.sqlite"))
    ap.add_argument("--kind", choices=["text", "notes", "bibliography", "index", "front"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--refs", action="store_true", help="list archive-citation paragraphs")
    ap.add_argument("--full", action="store_true", help="print full paragraph text")
    ap.add_argument("--context", type=int, default=0,
                    help="also print N paragraphs before/after each hit")
    args = ap.parse_args()
    if not args.refs and not args.query:
        ap.error("give a query or --refs")

    con = sqlite3.connect(args.db)
    rows = refs(con, args.limit) if args.refs else search(con, args.query, args.kind, args.limit)
    for pid, kind, section, page, seq, snip, text in rows:
        print(f"[{kind} {section} p.{page} #{seq}] {text if args.full or args.refs else snip}")
        if args.context:
            for ctx in con.execute(
                "SELECT text FROM passages WHERE id BETWEEN ? AND ? AND id != ? "
                "AND section = (SELECT section FROM passages WHERE id = ?) ORDER BY id",
                (pid - args.context, pid + args.context, pid, pid),
            ):
                print(f"    ~ {ctx[0][:200]}")
        print()
    print(f"{len(rows)} hit(s)")


if __name__ == "__main__":
    main()
