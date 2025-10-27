from __future__ import annotations
import os
import aiosqlite
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site TEXT NOT NULL,
  title TEXT,
  payout TEXT,
  date_posted TEXT,
  location TEXT,
  method TEXT,
  link TEXT NOT NULL,
  description TEXT,
  image_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(site, link)
);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  message_id INTEGER NOT NULL,
  posted_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE,
  UNIQUE(listing_id)
);

CREATE TABLE IF NOT EXISTS rejects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER,
  site TEXT NOT NULL,
  link TEXT NOT NULL,
  rejected_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(site, link),
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  q TEXT,
  min_amount INTEGER,
  location TEXT,
  method TEXT,
  site TEXT,
  remote_only INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS auto_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  min_amount INTEGER,
  require_remote INTEGER NOT NULL DEFAULT 0,
  site_contains TEXT,
  method_contains TEXT,
  location_contains TEXT,
  channel_id INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS moderation_cards (
  listing_id INTEGER PRIMARY KEY,
  channel_id INTEGER NOT NULL,
  message_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(listing_id) REFERENCES listings(id) ON DELETE CASCADE
);
"""

def _get_val(obj: Any, key: str) -> Any:
    # Supports dict-like and attribute-like objects
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

class DB:
    def __init__(self, path: Optional[str] = None) -> None:
        if path:
            self.db_path = path
        else:
            url = os.getenv("DATABASE_URL", "")
            if url.startswith("sqlite:///"):
                self.db_path = url.replace("sqlite:///", "", 1)
            else:
                self.db_path = os.getenv("DB_PATH", "clickcartel.db")
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        if self.conn:
            return
        base = os.path.dirname(self.db_path)
        if base:
            os.makedirs(base, exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    # ---- Scrape ingest ----
    async def upsert_listings(self, listings: List[Any]) -> Tuple[int, int]:
        """
        Insert/update scraped listings that may be dicts or objects.
        Returns (new_rows_inserted, pending_count_after).
        """
        assert self.conn is not None, "DB not connected"
        new_count = 0
        for it in listings:
            site = (_get_val(it, "site") or "").strip()
            link = (_get_val(it, "link") or "").strip()
            if not site or not link:
                continue
            cur = await self.conn.execute("SELECT id FROM listings WHERE site=? AND link=?", (site, link))
            row = await cur.fetchone()
            fields = (
                _get_val(it, "title"),
                _get_val(it, "payout"),
                _get_val(it, "date_posted"),
                _get_val(it, "location"),
                _get_val(it, "method"),
                link,
                _get_val(it, "description"),
                _get_val(it, "image_url"),
                site,
                link,
            )
            if row:
                await self.conn.execute("""
                    UPDATE listings
                    SET title=?, payout=?, date_posted=?, location=?, method=?, link=?, description=?, image_url=?, updated_at=datetime('now')
                    WHERE site=? AND link=?
                """, fields)
            else:
                await self.conn.execute("""
                    INSERT INTO listings (title, payout, date_posted, location, method, link, description, image_url, site)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    _get_val(it, "title"), _get_val(it, "payout"), _get_val(it, "date_posted"),
                    _get_val(it, "location"), _get_val(it, "method"), link,
                    _get_val(it, "description"), _get_val(it, "image_url"), site
                ))
                new_count += 1
        await self.conn.commit()
        # Pending = no post and no reject
        cur = await self.conn.execute("""
            SELECT COUNT(*)
            FROM listings l
            LEFT JOIN posts p ON p.listing_id = l.id
            LEFT JOIN rejects r ON r.listing_id = l.id OR (r.site = l.site AND r.link = l.link)
            WHERE p.listing_id IS NULL AND r.id IS NULL
        """)
        pending = int((await cur.fetchone())[0])
        return new_count, pending

    # ---- Review queue helpers ----
    async def get_pending_reviews(self) -> List[Any]:
        assert self.conn is not None, "DB not connected"
        cur = await self.conn.execute("""
            SELECT l.*
            FROM listings l
            LEFT JOIN posts p ON p.listing_id = l.id
            LEFT JOIN rejects r ON r.listing_id = l.id OR (r.site = l.site AND r.link = l.link)
            WHERE p.listing_id IS NULL AND r.id IS NULL
            ORDER BY l.id DESC
        """)
        return await cur.fetchall()

    async def mark_review_posted(self, listing_id: int, message_id: int, channel_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute(
            "INSERT OR REPLACE INTO posts (listing_id, channel_id, message_id) VALUES (?, ?, ?)",
            (listing_id, channel_id, message_id),
        )
        await self.conn.commit()

    async def mark_review_rejected(self, listing_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        cur = await self.conn.execute("SELECT site, link FROM listings WHERE id=?", (listing_id,))
        row = await cur.fetchone()
        if row:
            await self.conn.execute(
                "INSERT OR IGNORE INTO rejects (listing_id, site, link) VALUES (?, ?, ?)",
                (listing_id, row["site"], row["link"]),
            )
            await self.conn.commit()

    async def update_listing_fields(self, listing_id: int, **fields: Any) -> None:
        assert self.conn is not None, "DB not connected"
        allowed = {"title", "payout", "location", "method", "description", "image_url", "date_posted"}
        sets: List[str] = []
        args: List[Any] = []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                args.append(v)
        if not sets:
            return
        args.append(listing_id)
        await self.conn.execute(f"UPDATE listings SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", args)
        await self.conn.commit()

    async def clear_listings(self) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute("DELETE FROM posts")
        await self.conn.execute("DELETE FROM rejects")
        await self.conn.execute("DELETE FROM moderation_cards")
        await self.conn.execute("DELETE FROM listings")
        await self.conn.commit()

    # ---- Moderation announce persistence ----
    async def get_unannounced_pending_for_mod(self) -> List[Any]:
        assert self.conn is not None, "DB not connected"
        cur = await self.conn.execute("""
            SELECT l.*
            FROM listings l
            LEFT JOIN posts p ON p.listing_id = l.id
            LEFT JOIN rejects r ON r.listing_id = l.id OR (r.site = l.site AND r.link = l.link)
            LEFT JOIN moderation_cards m ON m.listing_id = l.id
            WHERE p.listing_id IS NULL
              AND r.id IS NULL
              AND m.listing_id IS NULL
            ORDER BY l.id DESC
        """)
        return await cur.fetchall()

    async def mark_moderation_announced(self, listing_id: int, channel_id: int, message_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute(
            "INSERT OR REPLACE INTO moderation_cards (listing_id, channel_id, message_id) VALUES (?, ?, ?)",
            (listing_id, channel_id, message_id),
        )
        await self.conn.commit()

    async def clear_moderation_card(self, listing_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute("DELETE FROM moderation_cards WHERE listing_id=?", (listing_id,))
        await self.conn.commit()

    # ---- Saved searches API ----
    async def add_saved_search(self, user_id: int, name: str, params: Dict[str, Any]) -> int:
        assert self.conn is not None, "DB not connected"
        q = """INSERT OR REPLACE INTO saved_searches
               (user_id, name, q, min_amount, location, method, site, remote_only, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)"""
        await self.conn.execute(q, (
            user_id, name, params.get("q"), params.get("min_amount"),
            params.get("location"), params.get("method"), params.get("site"),
            1 if params.get("remote_only") else 0,
        ))
        await self.conn.commit()
        cur = await self.conn.execute("SELECT id FROM saved_searches WHERE user_id=? AND name=?", (user_id, name))
        row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def list_saved_searches(self, user_id: int) -> List[Any]:
        assert self.conn is not None, "DB not connected"
        cur = await self.conn.execute("""
            SELECT id, name, q, min_amount, location, method, site, remote_only, enabled, created_at
            FROM saved_searches WHERE user_id=? ORDER BY created_at DESC
        """, (user_id,))
        return await cur.fetchall()

    async def delete_saved_search(self, user_id: int, search_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute("DELETE FROM saved_searches WHERE user_id=? AND id=?", (user_id, search_id))
        await self.conn.commit()

    async def iter_saved_searches(self) -> List[Any]:
        assert self.conn is not None, "DB not connected"
        cur = await self.conn.execute("SELECT * FROM saved_searches WHERE enabled=1")
        return await cur.fetchall()

    # ---- Auto rules API ----
    async def add_rule(self, name: str, params: Dict[str, Any]) -> int:
        assert self.conn is not None, "DB not connected"
        q = """INSERT INTO auto_rules
               (name, min_amount, require_remote, site_contains, method_contains, location_contains, channel_id, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)"""
        await self.conn.execute(q, (
            name, params.get("min_amount"), 1 if params.get("require_remote") else 0,
            params.get("site_contains"), params.get("method_contains"),
            params.get("location_contains"), params.get("channel_id"),
        ))
        await self.conn.commit()
        cur = await self.conn.execute("SELECT id FROM auto_rules WHERE name=? ORDER BY id DESC LIMIT 1", (name,))
        row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def list_rules(self, enabled_only: bool = False) -> List[Any]:
        assert self.conn is not None, "DB not connected"
        if enabled_only:
            cur = await self.conn.execute("SELECT * FROM auto_rules WHERE enabled=1 ORDER BY id ASC")
        else:
            cur = await self.conn.execute("SELECT * FROM auto_rules ORDER BY id ASC")
        return await cur.fetchall()

    async def toggle_rule(self, rule_id: int, enabled: bool) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute("UPDATE auto_rules SET enabled=? WHERE id=?", (1 if enabled else 0, rule_id))
        await self.conn.commit()

    async def delete_rule(self, rule_id: int) -> None:
        assert self.conn is not None, "DB not connected"
        await self.conn.execute("DELETE FROM auto_rules WHERE id=?", (rule_id,))
        await self.conn.commit()