"""
gemini.py — Generate smart Instagram comment replies using Google Gemini
Requires env var:
  GEMINI_API_KEY   — your Google AI Studio API key
  GEMINI_TONE      — optional: friendly | professional | funny | casual (default: friendly)
"""

import os
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"


def generate_reply(post_context: str, comment_text: str, commenter: str = "") -> str:
    """
    Given what the post is about and a user comment, generate a natural reply.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    tone = os.getenv("GEMINI_TONE", "friendly")
    brand_name = os.getenv("BRAND_NAME", "us")

    commenter_line = f"The commenter's username is @{commenter}." if commenter else ""

    prompt = f"""You are a social media manager replying to Instagram comments on behalf of {brand_name}.

POST CONTEXT:
{post_context}

{commenter_line}
COMMENT: "{comment_text}"

Write a {tone}, short, genuine Instagram reply to this comment. Rules:
- Max 2 sentences. Keep it concise.
- Sound human, not robotic or overly formal.
- Be relevant to the post content above.
- Do NOT use hashtags.
- Do NOT use emojis unless the comment is very casual/funny.
- If the comment is a question, answer it based on the post context.
- If the comment is negative/rude, respond politely and professionally.
- Do NOT include any prefix like "Reply:" or quotes around your answer.
- Just write the reply text directly.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 150,
        },
    }

    resp = requests.post(
        f"{GEMINI_URL}?key={api_key}",
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Clean up any accidental quotes
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        return reply
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from e
