#!/usr/bin/env python3
"""
Lightweight RSS fetcher that polls an RSS/ATOM feed, deduplicates by guid/link,
and stores items into a local SQLite database. Uses only Python stdlib so it's
easy to run on Windows without extra installs.

Basic usage:
  python scripts\rss_fetcher.py --url "https://data.gmanetwork.com/gno/rss/news/regions/feed.xml" --once

Run as a 24/7 poller:
  python scripts\rss_fetcher.py --url <FEED_URL> --interval 300

The script stores items in the SQLite DB at `--db` (default: data/rss_items.db).
"""
import argparse
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import os
import signal
import sys
import json

STOP = False


def handle_signal(signum, frame):
    global STOP
    logging.info("Received stop signal (%s). Will exit after current fetch.", signum)
    STOP = True


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def ensure_dir_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


class RSSDB:
    def __init__(self, path):
        ensure_dir_for_file(path)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                guid TEXT UNIQUE,
                title TEXT,
                link TEXT,
                published TEXT,
                summary TEXT,
                fetched_at TEXT
            )
            """
        )
        self.conn.commit()

    def save_items(self, items):
        cur = self.conn.cursor()
        inserted = 0
        for it in items:
            try:
                cur.execute(
                    "INSERT INTO items (guid, title, link, published, summary, fetched_at) VALUES (?,?,?,?,?,?)",
                    (
                        it.get("guid"),
                        it.get("title"),
                        it.get("link"),
                        it.get("published"),
                        it.get("summary"),
                        datetime.utcnow().isoformat() + "Z",
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # duplicate guid, skip
                continue
        self.conn.commit()
        return inserted


def export_db_to_json(db_path, out_path=None):
    """Export the current `items` table to a JSONL file. Used to create a quick snapshot json.

    If out_path is None, defaults to data/rss_items.jsonl beside the DB.
    """
    if out_path is None:
        # default to workspace-level data/rss_items.jsonl (parent of scripts)
        out_path = os.path.abspath(os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "rss_items.jsonl")))
    # ensure output dir exists
    d = os.path.dirname(out_path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

    import re
    import html as _html

    def clean_summary_for_snapshot(s):
        if not s:
            return None
        # remove common cookie/privacy phrases similar to exporter
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
        s = _html.unescape(s)
        s = re.sub(r"\s+", " ", s).strip()
        return s if s else None

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("SELECT guid, title, link, published, summary, fetched_at FROM items ORDER BY fetched_at ASC")
    except sqlite3.OperationalError:
        # table might not exist yet
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("")
        return 0

    written = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for row in cur:
            guid, title, link, published, summary, fetched_at = row
            cleaned = clean_summary_for_snapshot(summary)
            obj = {
                "guid": guid,
                "title": title,
                "link": link,
                "published": published,
                "summary": cleaned,
                "fetched_at": fetched_at,
            }
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1

    return written


def _localname(tag):
    # handle namespaces: {ns}local -> local
    if tag is None:
        return None
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def parse_rss(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []

    # Try common paths: channel/item (RSS) or entry (Atom)
    # Find all elements where localname == 'item' or 'entry'
    for elem in root.findall('.//'):
        if _localname(elem.tag) in ("item", "entry"):
            item = elem
            data = {}
            # collect typical children
            for child in item:
                name = _localname(child.tag)
                text = child.text.strip() if child.text and child.text.strip() else None
                if name == "guid":
                    data["guid"] = text
                elif name == "link":
                    # link in Atom may be an element with href attribute
                    href = child.attrib.get("href")
                    data.setdefault("link", href or text)
                elif name in ("title", "description", "summary", "content"):
                    # prefer title/description/summary
                    if name == "title":
                        data["title"] = text
                    else:
                        # if no summary yet, use description/summary/content
                        data.setdefault("summary", text)
                elif name in ("pubDate", "published", "updated"):
                    data.setdefault("published", text)

            # if no guid, use link
            if not data.get("guid"):
                data["guid"] = data.get("link")

            # fallback title/summary
            data.setdefault("title", data.get("summary") or "(no title)")
            items.append(data)

    return items


def fetch_feed(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "rss-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
    return content


def run_poll(urls, db_path, interval, once=False):
    # Support both single URL string and list of URLs
    if isinstance(urls, str):
        urls = [urls]
    
    logging.info("Starting fetcher: urls=%s interval=%s db=%s once=%s", urls, interval, db_path, once)
    db = RSSDB(db_path)

    # create initial JSON snapshot (empty if no rows yet)
    try:
        exported = export_db_to_json(db_path, os.path.join(os.path.dirname(db_path) or "data", "rss_items.jsonl"))
        logging.info("Initial JSON snapshot written, %d rows", exported)
    except Exception:
        logging.exception("Failed to write initial JSON snapshot")

    while True:
        if STOP:
            logging.info("Stop requested. Exiting loop.")
            break

        total_added = 0
        for url in urls:
            try:
                logging.info("Fetching feed: %s", url)
                xml = fetch_feed(url)
                items = parse_rss(xml)
                added = db.save_items(items)
                total_added += added
                logging.info("Feed %s: Fetched %d items, inserted %d new.", url, len(items), added)
            except Exception as e:
                logging.exception("Error fetching/parsing %s: %s", url, e)
        
        # if we inserted new rows, update the JSON snapshot as well
        if total_added > 0:
            try:
                exported = export_db_to_json(db_path, os.path.join(os.path.dirname(db_path) or "data", "rss_items.jsonl"))
                logging.info("Updated JSON snapshot, %d rows", exported)
            except Exception:
                logging.exception("Failed to update JSON snapshot after insert")

        if once:
            break

        # sleep but be interruptible
        slept = 0
        while slept < interval:
            if STOP:
                break
            to_sleep = min(1, interval - slept)
            time.sleep(to_sleep)
            slept += to_sleep


def main():
    parser = argparse.ArgumentParser(description="Lightweight RSS fetcher and sqlite archiver")
    # Updated default feeds with the Philippine news sources
    default_feeds = [
        "https://data.gmanetwork.com/gno/rss/news/regions/feed.xml",
        "https://tonite.abante.com.ph/feed/",
        "https://philnews.ph/feed/",
        "https://www.rappler.com/feed/",
        "https://www.inquirer.net/fullfeed/",
        "https://pilipinasdaily.com/feed/",
        "https://www.mindanaotimes.com.ph/feed/",
        "https://visayandailystar.com/feed/",
    ]
    parser.add_argument(
        "--url",
        action="append",
        help="RSS/Atom feed URL (can be specified multiple times, or defaults to Philippine news feeds)",
    )
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds (default 300)")
    parser.add_argument("--db", default=os.path.join("data", "rss_items.db"), help="SQLite DB path (default: data/rss_items.db)")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Use provided URLs or default feeds
    urls = args.url if args.url else default_feeds

    try:
        run_poll(urls, args.db, args.interval, once=args.once)
    except KeyboardInterrupt:
        logging.info("Interrupted by user, exiting")


if __name__ == "__main__":
    main()
