"""
instagram.py — Instagram Graph API helpers
Requires env vars:
  IG_ACCESS_TOKEN   — long-lived page/user access token
  IG_USER_ID        — your Instagram Business / Creator account ID
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


# ── Post context (caption + media type) ───────────────────────────────────

def get_post_context(post_id: str) -> dict:
    """
    Returns caption, media_type, transcript (if video), and a summary string.
    Caches the result in Cloud SQL so we don't hit the API repeatedly.
    """
    # Check cache first
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
    # IMAGE | VIDEO | CAROUSEL_ALBUM
    media_type = data.get("media_type", "IMAGE")
    permalink = data.get("permalink", "")
    transcript = ""

    # If it's a video/reel, transcribe the audio using insta-app logic
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

    # Build a plain-English summary for Gemini context
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
    """Returns list of {id, text, username, timestamp}."""
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
        # Pagination
        url = data.get("paging", {}).get("next")
        params = {}   # next URL already has token embedded
    return comments


# ── Post a reply ───────────────────────────────────────────────────────────

def post_reply(comment_id: str, message: str) -> dict:
    """Reply to a comment. Returns the API response dict."""
    url = f"{BASE}/{comment_id}/replies"
    resp = requests.post(url, data={
        "message":      message,
        "access_token": _token(),
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()
