"""
db.py — Cloud SQL (MySQL) connection + helpers
Now includes dm_logs table for DM reply tracking.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

_engine = None


def _get_engine():
    global _engine
    if _engine:
        return _engine

    host = os.getenv("CLOUD_SQL_HOST", "127.0.0.1")
    port = os.getenv("CLOUD_SQL_PORT", "3306")
    user = os.getenv("CLOUD_SQL_USER", "root")
    password = os.getenv("CLOUD_SQL_PASSWORD", "")
    database = os.getenv("CLOUD_SQL_DATABASE", "insta_replier")

    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    _engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    return _engine


def init_db():
    """Create all tables if they don't exist."""
    engine = _get_engine()
    with engine.connect() as conn:

        # Comment reply logs (existing)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reply_logs (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                post_id         VARCHAR(64)  NOT NULL,
                comment_id      VARCHAR(64)  NOT NULL UNIQUE,
                commenter       VARCHAR(128),
                comment_text    TEXT,
                reply_text      TEXT,
                post_context    TEXT,
                ig_reply_id     VARCHAR(64),
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_post_id (post_id),
                INDEX idx_created_at (created_at)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        # Post context cache (existing)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS post_cache (
                post_id         VARCHAR(64)  PRIMARY KEY,
                caption         TEXT,
                media_type      VARCHAR(32),
                transcript      TEXT,
                summary         TEXT,
                cached_at       DATETIME DEFAULT CURRENT_TIMESTAMP
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        # NEW: DM reply logs
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dm_logs (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                conversation_id VARCHAR(128),
                recipient_id    VARCHAR(64)  NOT NULL,
                sender_name     VARCHAR(128),
                message_text    TEXT,
                reply_text      TEXT,
                reel_url        TEXT,
                ig_message_id   VARCHAR(128),
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_recipient (recipient_id),
                INDEX idx_dm_created (created_at)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        conn.commit()
    print("[DB] Tables ready (reply_logs, post_cache, dm_logs).")


# ── Comment log helpers ────────────────────────────────────────────────────

def save_reply_log(*, post_id, comment_id, commenter, comment_text,
                   reply_text, post_context, ig_reply_id):
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO reply_logs
                (post_id, comment_id, commenter, comment_text,
                 reply_text, post_context, ig_reply_id)
            VALUES
                (:post_id, :comment_id, :commenter, :comment_text,
                 :reply_text, :post_context, :ig_reply_id)
            ON DUPLICATE KEY UPDATE
                reply_text  = VALUES(reply_text),
                ig_reply_id = VALUES(ig_reply_id)
        """), {
            "post_id": post_id, "comment_id": comment_id,
            "commenter": commenter, "comment_text": comment_text,
            "reply_text": reply_text, "post_context": post_context,
            "ig_reply_id": ig_reply_id,
        })
        conn.commit()


def get_all_logs(limit=200):
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, post_id, commenter, comment_text, reply_text,
                   ig_reply_id, created_at
            FROM reply_logs
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_stats():
    engine = _get_engine()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM reply_logs")).scalar()
        today = conn.execute(text(
            "SELECT COUNT(*) FROM reply_logs WHERE DATE(created_at) = CURDATE()"
        )).scalar()
        posts = conn.execute(text(
            "SELECT COUNT(DISTINCT post_id) FROM reply_logs"
        )).scalar()
        dm_total = conn.execute(text("SELECT COUNT(*) FROM dm_logs")).scalar()
        dm_today = conn.execute(text(
            "SELECT COUNT(*) FROM dm_logs WHERE DATE(created_at) = CURDATE()"
        )).scalar()
    return {
        "total_replies":  total,
        "replies_today":  today,
        "posts_handled":  posts,
        "dm_total":       dm_total,
        "dm_today":       dm_today,
    }


def cache_post(post_id, caption, media_type, transcript, summary):
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO post_cache (post_id, caption, media_type, transcript, summary)
            VALUES (:post_id, :caption, :media_type, :transcript, :summary)
            ON DUPLICATE KEY UPDATE
                caption=VALUES(caption), media_type=VALUES(media_type),
                transcript=VALUES(transcript), summary=VALUES(summary),
                cached_at=NOW()
        """), {"post_id": post_id, "caption": caption, "media_type": media_type,
               "transcript": transcript, "summary": summary})
        conn.commit()


def get_cached_post(post_id):
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT * FROM post_cache WHERE post_id = :pid"
        ), {"pid": post_id}).fetchone()
    return dict(row._mapping) if row else None


# ── DM log helpers ─────────────────────────────────────────────────────────

def save_dm_log(*, conversation_id, recipient_id, sender_name,
                message_text, reply_text, reel_url, ig_message_id):
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO dm_logs
                (conversation_id, recipient_id, sender_name,
                 message_text, reply_text, reel_url, ig_message_id)
            VALUES
                (:conversation_id, :recipient_id, :sender_name,
                 :message_text, :reply_text, :reel_url, :ig_message_id)
        """), {
            "conversation_id": conversation_id,
            "recipient_id":    recipient_id,
            "sender_name":     sender_name,
            "message_text":    message_text,
            "reply_text":      reply_text,
            "reel_url":        reel_url or "",
            "ig_message_id":   ig_message_id,
        })
        conn.commit()


def get_all_dm_logs(limit=200):
    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, conversation_id, sender_name, message_text,
                   reply_text, reel_url, ig_message_id, created_at
            FROM dm_logs
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
    return [dict(r._mapping) for r in rows]
