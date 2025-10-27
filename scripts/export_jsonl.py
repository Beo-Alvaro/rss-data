#!/usr/bin/env python3
"""
Export items stored in the SQLite DB to a JSONL file for downstream processing.

Usage examples:
  python scripts\export_jsonl.py --db data\rss_items.db --out data\rss_items.jsonl
  python scripts\export_jsonl.py --db data\rss_items.db --out data\recent.jsonl --since 2025-10-25T00:00:00Z --limit 100
"""
import argparse
import sqlite3
import json
import os
import logging
from datetime import datetime
import re
import html as _html


def ensure_dir_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def export(db_path, out_path, since=None, limit=None):
    ensure_dir_for_file(out_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    sql = "SELECT guid, title, link, published, summary, fetched_at FROM items"
    clauses = []
    params = []
    if since:
        clauses.append("fetched_at >= ?")
        params.append(since)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY fetched_at ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    logging.info("Running query: %s params=%s", sql, params)
    cur.execute(sql, params)

    written = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for row in cur:
            guid, title, link, published, summary, fetched_at = row
            # clean summary to remove cookie banners and other noise
            summary = clean_summary(summary)
            obj = {
                "guid": guid,
                "title": title,
                "link": link,
                "published": published,
                "summary": summary,
                "fetched_at": fetched_at,
            }
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1

    logging.info("Exported %d items to %s", written, out_path)
    return written


def clean_summary(text: str) -> str:
    """Remove common cookie-banner phrases and noisy fragments from feed summaries.

    This is a lightweight heuristic cleaner intended to remove obvious phrases like
    "We use cookies to ensure...", "I AGREE", "FIND OUT MORE", "ADVERTISEMENT",
    and other boilerplate that sometimes appears in feed descriptions.
    """
    if not text:
        return text

    s = text
    # common cookie/privacy phrases and boilerplate (case-insensitive)
    patterns = [
        r"we use cookies to ensure[\s\S]{0,200}",
        r"by continued use, you (agree|accept)[\s\S]{0,200}",
        r"click (find out more|here for more)",
        r"i agree",
        r"find out more",
        r"advertisement",
        r"filtered by:\s*\w+",
        r"read more",
        r"continue reading",
        r"subscribe",
    ]

    for p in patterns:
        s = re.sub(p, " ", s, flags=re.IGNORECASE)

    # strip HTML tags
    s = re.sub(r"<[^>]+>", " ", s)
    # decode HTML entities (e.g., &nbsp;, &amp;)
    s = _html.unescape(s)

    # remove any leftover multiple whitespace and trim
    s = re.sub(r"\s+", " ", s).strip()
    # if summary became empty, return None to signal missing summary
    return s if s else None


def main():
    parser = argparse.ArgumentParser(description="Export RSS items from sqlite DB to JSONL")
    default_db = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "rss_items.db"))
    default_out = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "rss_items.jsonl"))
    parser.add_argument("--db", default=default_db, help="SQLite DB path")
    parser.add_argument("--out", default=default_out, help="Output JSONL file path")
    parser.add_argument("--since", help="ISO timestamp (inclusive) to export items fetched since, e.g. 2025-10-25T00:00:00Z")
    parser.add_argument("--limit", type=int, help="Limit number of exported rows")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.since:
        # Basic validation
        try:
            # allow either with or without trailing Z
            _ = datetime.fromisoformat(args.since.replace("Z", ""))
        except Exception as e:
            logging.error("Invalid --since timestamp: %s", e)
            raise

    if not os.path.exists(args.db):
        logging.error("DB file not found: %s", args.db)
        raise SystemExit(1)

    exported = export(args.db, args.out, since=args.since, limit=args.limit)
    print(f"Exported {exported} items to {args.out}")


if __name__ == "__main__":
    main()
