"""
instagram.py — Instagram Graph API helpers
"""

import os
import requests
from db import cache_post, get_cached_post

BASE = "https://graph.instagram.com/v19.0"


def _token():
    t = os.getenv("IG_ACCESS_TOKEN", "")
    if not t:
        raise ValueError("IG_ACCESS_TOKEN not set in .env")
    return t


def _ig_user_id():
    uid = os.getenv("IG_USER_ID", "")
    if not uid:
        raise ValueError("IG_USER_ID not set in .env")
    return uid


# ── Fetch your recent posts automatically ──────────────────────────────────

def get_recent_posts(limit=12):
    """
    Fetch the account's recent posts automatically.
    Uses the correct Facebook Graph API endpoint for Instagram Business accounts.
    """
    url = f"{BASE}/{_ig_user_id()}/media"
    params = {
        "fields": "id,caption,media_type,thumbnail_url,media_url,permalink,timestamp",
        "access_token": _token(),
        "limit": limit,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        # Try fallback with fewer fields if thumbnail_url causes issues
        params["fields"] = "id,caption,media_type,permalink,timestamp"
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

    posts = []
    for p in data.get("data", []):
        posts.append({
            "id":            p.get("id"),
            "caption":       (p.get("caption") or "")[:120],
            "media_type":    p.get("media_type", "IMAGE"),
            "thumbnail_url": p.get("thumbnail_url") or p.get("media_url", ""),
            "permalink":     p.get("permalink", ""),
            "timestamp":     p.get("timestamp", ""),
        })
    return posts


# ── Post context (caption + transcript) ───────────────────────────────────

def get_post_context(post_id: str) -> dict:
    cached = get_cached_post(post_id)
    if cached:
        return cached

    url = f"{BASE}/{post_id}"
    params = {
        "fields": "caption,media_type,media_url,permalink",
        "access_token": _token(),
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    caption = data.get("caption", "")
    media_type = data.get("media_type", "IMAGE")
    permalink = data.get("permalink", "")
    transcript = ""

    if media_type == "VIDEO" and permalink:
        try:
            import sys
            import os as _os
            sys.path.insert(0, _os.path.join(
                _os.path.dirname(__file__), '..', 'insta-app'))
            from app import transcribe_reel
            transcript = transcribe_reel(permalink)
        except Exception as e:
            transcript = f"(Transcription unavailable: {e})"

    parts = []
    if caption:
        parts.append(f"Caption: {caption}")
    if transcript:
        parts.append(f"Audio transcript: {transcript}")
    summary = "\n".join(parts) if parts else "No content available."

    result = {
        "post_id":    post_id,
        "caption":    caption,
        "media_type": media_type,
        "transcript": transcript,
        "summary":    summary,
        "permalink":  permalink,
    }

    cache_post(post_id, caption, media_type, transcript, summary)
    return result


# ── Fetch comments ─────────────────────────────────────────────────────────

def fetch_post_comments(post_id: str) -> list:
    url = f"{BASE}/{post_id}/comments"
    params = {
        "fields": "id,text,username,timestamp",
        "access_token": _token(),
    }
    comments = []
    while url:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for c in data.get("data", []):
            comments.append({
                "id":        c.get("id"),
                "text":      c.get("text", ""),
                "username":  c.get("username", ""),
                "timestamp": c.get("timestamp", ""),
            })
        url = data.get("paging", {}).get("next")
        params = {}
    return comments


# ── Post a reply ───────────────────────────────────────────────────────────

def post_reply(comment_id: str, message: str) -> dict:
    url = f"{BASE}/{comment_id}/replies"
    resp = requests.post(url, data={
        "message":      message,
        "access_token": _token(),
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()
