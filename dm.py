import os
import requests

BASE = "https://graph.instagram.com/v19.0"


def _token():
    return os.getenv("IG_ACCESS_TOKEN", "")


def _ig_user_id():
    return os.getenv("IG_USER_ID", "")


def _page_id():
    return os.getenv("IG_PAGE_ID", "")


def get_conversations(limit=20):
    url = f"{BASE}/{_ig_user_id()}/conversations"
    params = {
        "platform": "instagram",
        "fields": "id,participants,updated_time,message_count",
        "access_token": _token(),
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_conversation_messages(conversation_id, limit=10):
    url = f"{BASE}/{conversation_id}/messages"
    params = {
        "fields": "id,message,from,created_time,attachments,shares",
        "access_token": _token(),
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    messages = resp.json().get("data", [])
    result = []
    for msg in messages:
        item = {
            "id": msg.get("id"),
            "text": msg.get("message", ""),
            "from_id": msg.get("from", {}).get("id", ""),
            "from_name": msg.get("from", {}).get("name", ""),
            "created_time": msg.get("created_time", ""),
            "is_reel": False,
            "reel_url": None,
            "reel_id": None,
        }
        for share in msg.get("shares", {}).get("data", []):
            link = share.get("link", "")
            if "reel" in link:
                item["is_reel"] = True
                item["reel_url"] = link
                break
        for att in msg.get("attachments", {}).get("data", []):
            if att.get("type") in ("ig_reel", "share"):
                item["is_reel"] = True
                item["reel_url"] = att.get("payload", {}).get("url", "")
                break
        result.append(item)
    return result


def send_dm_reply(recipient_id, message):
    page_id = _page_id()
    url = f"{BASE}/{page_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message},
        "messaging_type": "RESPONSE",
        "access_token": _token(),
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_reel_context_from_url(reel_url):
    import re
    import sys
    import os as _os
    match = re.search(
        r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)", reel_url)
    if not match:
        return {"summary": f"Shared reel: {reel_url}", "caption": "", "transcript": ""}
    try:
        sys.path.insert(0, _os.path.join(
            _os.path.dirname(__file__), '..', 'insta-app'))
        from app import transcribe_reel
        transcript = transcribe_reel(reel_url)
    except Exception:
        transcript = ""
    return {
        "summary": f"User shared a Reel. Audio: {transcript}" if transcript else f"User shared a Reel: {reel_url}",
        "caption": "",
        "transcript": transcript,
    }
