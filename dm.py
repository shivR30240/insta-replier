"""
dm.py — Instagram Direct Message (DM) handler
Handles fetching DMs, reading reel shares in DMs, and sending replies.

Requires env vars:
  IG_ACCESS_TOKEN   — long-lived access token
  IG_USER_ID        — Instagram Business account ID
  IG_PAGE_ID        — Facebook Page ID linked to Instagram
"""

import os
import requests

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


# ── Fetch all DM conversations ─────────────────────────────────────────────

def _page_id():
    pid = os.getenv("IG_PAGE_ID", "")
    if not pid:
        raise ValueError("IG_PAGE_ID not set in .env")
    return pid


def get_conversations(limit=20):
    """
    Returns list of active DM conversations.
    """
    url = f"{BASE}/{_page_id()}/conversations"

    params = {
        "platform": "instagram",
        "fields": "id,participants,updated_time,message_count",
        "access_token": _token(),
        "limit": limit,
    }

    resp = requests.get(url, params=params, timeout=15)

    print(resp.text)   # VERY IMPORTANT FOR DEBUGGING

    resp.raise_for_status()

    data = resp.json()

    return data.get("data", [])


# ── Fetch messages inside a conversation ──────────────────────────────────

def get_conversation_messages(conversation_id: str, limit=10):
    """
    Returns list of messages in a conversation.
    Each message has: id, message, from, created_time, attachments (if reel)
    """
    url = f"{BASE}/{conversation_id}/messages"
    params = {
        "fields":       "id,message,from,created_time,attachments,shares",
        "access_token": _token(),
        "limit":        limit,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    messages = data.get("data", [])

    result = []
    for msg in messages:
        item = {
            "id":           msg.get("id"),
            "text":         msg.get("message", ""),
            "from_id":      msg.get("from", {}).get("id", ""),
            "from_name":    msg.get("from", {}).get("name", ""),
            "created_time": msg.get("created_time", ""),
            "is_reel":      False,
            "reel_url":     None,
            "reel_id":      None,
        }

        # Check if message contains a shared reel
        shares = msg.get("shares", {}).get("data", [])
        for share in shares:
            link = share.get("link", "")
            if "reel" in link or "instagram.com/reel" in link:
                item["is_reel"] = True
                item["reel_url"] = link
                item["reel_id"] = share.get("id", "")
                break

        # Also check attachments
        attachments = msg.get("attachments", {}).get("data", [])
        for att in attachments:
            if att.get("type") in ("ig_reel", "share"):
                item["is_reel"] = True
                item["reel_url"] = att.get("payload", {}).get("url", "")
                break

        result.append(item)

    return result


# ── Send a DM reply ────────────────────────────────────────────────────────

def send_dm_reply(recipient_id: str, message: str) -> dict:
    """
    Send a DM reply to a user by their Instagram-scoped user ID.
    """
    url = f"{BASE}/me/messages"
    payload = {
        "recipient":    {"id": recipient_id},
        "message":      {"text": message},
        "access_token": _token(),
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Get reel context from a shared reel URL ────────────────────────────────

def get_reel_context_from_url(reel_url: str) -> dict:
    """
    Given a reel URL shared in DM, extract its shortcode
    and fetch caption + transcript using the existing insta-app logic.
    """
    import re
    import sys
    import os as _os

    # Extract shortcode from URL
    match = re.search(
        r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)", reel_url)
    if not match:
        return {"summary": f"Shared reel: {reel_url}", "caption": "", "transcript": ""}

    shortcode = match.group(1)

    # Try to get post context via Graph API using shortcode
    # (shortcode → media ID lookup)
    try:
        sys.path.insert(0, _os.path.join(
            _os.path.dirname(__file__), '..', 'insta-app'))
        from app import transcribe_reel
        transcript = transcribe_reel(reel_url)
    except Exception as e:
        transcript = ""

    return {
        "summary":    f"User shared a Reel. Audio transcript: {transcript}" if transcript else f"User shared a Reel from: {reel_url}",
        "caption":    "",
        "transcript": transcript,
    }
