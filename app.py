from dm import get_conversations, get_conversation_messages, send_dm_reply, get_reel_context_from_url
from gemini import generate_reply
from instagram import fetch_post_comments, post_reply, get_post_context
from db import init_db, save_reply_log, get_all_logs, get_stats, save_dm_log, get_all_dm_logs
import os
import sys
import traceback
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'insta-app'))


app = Flask(__name__)

init_db()


# ──────────────────────────────────────────────────────────────────────────
#  EXISTING COMMENT ROUTES (unchanged)
# ──────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/post-context", methods=["POST"])
def api_post_context():
    data = request.get_json()
    post_id = data.get("post_id", "").strip()
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    try:
        ctx = get_post_context(post_id)
        return jsonify(ctx)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/comments", methods=["POST"])
def api_comments():
    data = request.get_json()
    post_id = data.get("post_id", "").strip()
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    try:
        comments = fetch_post_comments(post_id)
        return jsonify({"comments": comments})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-reply", methods=["POST"])
def api_generate_reply():
    data = request.get_json()
    comment_text = data.get("comment_text", "").strip()
    post_context = data.get("post_context", "")
    commenter = data.get("commenter", "")
    if not comment_text:
        return jsonify({"error": "comment_text is required"}), 400
    try:
        reply = generate_reply(post_context, comment_text, commenter)
        return jsonify({"reply": reply})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/post-reply", methods=["POST"])
def api_post_reply():
    data = request.get_json()
    comment_id = data.get("comment_id", "").strip()
    post_id = data.get("post_id", "").strip()
    reply_text = data.get("reply_text", "").strip()
    comment_text = data.get("comment_text", "")
    commenter = data.get("commenter", "")
    post_context = data.get("post_context", "")

    if not all([comment_id, post_id, reply_text]):
        return jsonify({"error": "comment_id, post_id and reply_text are required"}), 400

    try:
        ig_response = post_reply(comment_id, reply_text)
        save_reply_log(
            post_id=post_id,
            comment_id=comment_id,
            commenter=commenter,
            comment_text=comment_text,
            reply_text=reply_text,
            post_context=post_context,
            ig_reply_id=ig_response.get("id", ""),
        )
        return jsonify({"success": True, "ig_reply_id": ig_response.get("id", "")})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs", methods=["GET"])
def api_logs():
    try:
        logs = get_all_logs()
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    try:
        return jsonify(get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  NEW DM ROUTES
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/dm/conversations", methods=["GET"])
def api_dm_conversations():
    """Fetch all DM conversations."""
    try:
        convos = get_conversations()
        return jsonify({"conversations": convos})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/messages", methods=["POST"])
def api_dm_messages():
    """Fetch messages in a conversation."""
    data = request.get_json()
    conversation_id = data.get("conversation_id", "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    try:
        messages = get_conversation_messages(conversation_id)
        return jsonify({"messages": messages})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/generate-reply", methods=["POST"])
def api_dm_generate_reply():
    """Generate a Gemini reply for a DM message, with reel context if applicable."""
    data = request.get_json()
    message_text = data.get("message_text", "").strip()
    sender_name = data.get("sender_name", "")
    reel_url = data.get("reel_url", "")
    post_context = data.get("post_context", "")

    # If a reel was shared, get its context
    if reel_url and not post_context:
        try:
            ctx = get_reel_context_from_url(reel_url)
            post_context = ctx.get("summary", "")
        except Exception:
            post_context = f"User shared a reel: {reel_url}"

    if not message_text and not reel_url:
        return jsonify({"error": "message_text or reel_url is required"}), 400

    # If only a reel was shared with no text, generate a context-aware reply
    if not message_text:
        message_text = "[User shared a Reel]"

    try:
        reply = generate_reply(post_context, message_text, sender_name)
        return jsonify({"reply": reply})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/send-reply", methods=["POST"])
def api_dm_send_reply():
    """Send a DM reply and log it to Cloud SQL."""
    data = request.get_json()
    recipient_id = data.get("recipient_id", "").strip()
    conversation_id = data.get("conversation_id", "").strip()
    reply_text = data.get("reply_text", "").strip()
    message_text = data.get("message_text", "")
    sender_name = data.get("sender_name", "")
    reel_url = data.get("reel_url", "")

    if not all([recipient_id, reply_text]):
        return jsonify({"error": "recipient_id and reply_text are required"}), 400

    try:
        ig_resp = send_dm_reply(recipient_id, reply_text)
        save_dm_log(
            conversation_id=conversation_id,
            recipient_id=recipient_id,
            sender_name=sender_name,
            message_text=message_text,
            reply_text=reply_text,
            reel_url=reel_url,
            ig_message_id=ig_resp.get("message_id", ""),
        )
        return jsonify({"success": True, "ig_message_id": ig_resp.get("message_id", "")})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/logs", methods=["GET"])
def api_dm_logs():
    """Return all DM reply logs."""
    try:
        logs = get_all_dm_logs()
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  WEBHOOK (handles both comments AND DMs)
# ──────────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == os.getenv("WEBHOOK_VERIFY_TOKEN"):
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                val = change.get("value", {})

                # ── Comment webhook ──
                if field == "comments":
                    comment_id = val.get("id")
                    comment_text = val.get("text", "")
                    commenter = val.get("from", {}).get("username", "user")
                    post_id = val.get("media", {}).get("id", "")
                    if comment_id and post_id:
                        ctx = get_post_context(post_id)
                        post_context = ctx.get("summary", "")
                        reply = generate_reply(
                            post_context, comment_text, commenter)
                        ig_resp = post_reply(comment_id, reply)
                        save_reply_log(
                            post_id=post_id, comment_id=comment_id,
                            commenter=commenter, comment_text=comment_text,
                            reply_text=reply, post_context=post_context,
                            ig_reply_id=ig_resp.get("id", ""),
                        )

                # ── DM webhook ──
                elif field == "messages":
                    messaging = val.get("messaging", [])
                    for msg_event in messaging:
                        sender_id = msg_event.get("sender", {}).get("id", "")
                        sender_name = msg_event.get(
                            "sender", {}).get("name", "")
                        msg = msg_event.get("message", {})
                        msg_text = msg.get("text", "")
                        attachments = msg.get("attachments", [])

                        # Skip messages sent by us
                        ig_user_id = os.getenv("IG_USER_ID", "")
                        if sender_id == ig_user_id:
                            continue

                        reel_url = ""
                        post_context = ""

                        # Check for reel in attachments
                        for att in attachments:
                            if att.get("type") in ("ig_reel", "share", "story_mention"):
                                reel_url = att.get(
                                    "payload", {}).get("url", "")
                                if reel_url:
                                    ctx = get_reel_context_from_url(reel_url)
                                    post_context = ctx.get("summary", "")
                                break

                        if not msg_text and not reel_url:
                            continue

                        display_text = msg_text or "[Shared a Reel]"
                        reply = generate_reply(
                            post_context, display_text, sender_name)
                        ig_resp = send_dm_reply(sender_id, reply)
                        save_dm_log(
                            conversation_id="",
                            recipient_id=sender_id,
                            sender_name=sender_name,
                            message_text=display_text,
                            reply_text=reply,
                            reel_url=reel_url,
                            ig_message_id=ig_resp.get("message_id", ""),
                        )

    except Exception:
        traceback.print_exc()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
