from dm import get_conversations, get_conversation_messages, send_dm_reply, get_reel_context_from_url
from gemini import generate_reply
from instagram import get_recent_posts, fetch_post_comments, post_reply, get_post_context
from db import (init_db, save_reply_log, get_all_logs, get_stats,
                save_dm_log, get_all_dm_logs, get_setting, set_setting,
                is_auto_reply_enabled, is_comment_already_replied)
import os
import sys
import traceback
from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'insta-app'))


app = Flask(__name__)
init_db()


# ──────────────────────────────────────────────────────────────────────────
#  PAGES
# ──────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory('templates', 'index.html')


# ──────────────────────────────────────────────────────────────────────────
#  POSTS — auto-fetch
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/posts", methods=["GET"])
def api_posts():
    """Return recent posts automatically — no post ID needed."""
    try:
        posts = get_recent_posts(limit=12)
        return jsonify({"posts": posts})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


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


# ──────────────────────────────────────────────────────────────────────────
#  COMMENTS
# ──────────────────────────────────────────────────────────────────────────

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
        save_reply_log(post_id=post_id, comment_id=comment_id, commenter=commenter,
                       comment_text=comment_text, reply_text=reply_text,
                       post_context=post_context, ig_reply_id=ig_response.get("id", ""))
        return jsonify({"success": True, "ig_reply_id": ig_response.get("id", "")})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  BULK REPLY — generate + post replies to ALL comments at once
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/bulk-reply", methods=["POST"])
def api_bulk_reply():
    """
    Generate and post replies to all comments on a post in one go.
    Skips comments already replied to.
    Returns per-comment results.
    """
    data = request.get_json()
    post_id = data.get("post_id", "").strip()
    post_context = data.get("post_context", "")

    if not post_id:
        return jsonify({"error": "post_id is required"}), 400

    results = []
    try:
        comments = fetch_post_comments(post_id)

        for c in comments:
            comment_id = c["id"]
            comment_text = c["text"]
            commenter = c["username"]

            # Skip if already replied
            if is_comment_already_replied(comment_id):
                results.append({"comment_id": comment_id, "commenter": commenter,
                                "status": "skipped", "reason": "already replied"})
                continue

            try:
                reply = generate_reply(post_context, comment_text, commenter)
                ig_resp = post_reply(comment_id, reply)
                save_reply_log(post_id=post_id, comment_id=comment_id, commenter=commenter,
                               comment_text=comment_text, reply_text=reply,
                               post_context=post_context, ig_reply_id=ig_resp.get("id", ""))
                results.append({"comment_id": comment_id, "commenter": commenter,
                                "status": "success", "reply": reply})
            except Exception as e:
                results.append({"comment_id": comment_id, "commenter": commenter,
                                "status": "error", "reason": str(e)})

        success_count = sum(1 for r in results if r["status"] == "success")
        skip_count = sum(1 for r in results if r["status"] == "skipped")
        error_count = sum(1 for r in results if r["status"] == "error")

        return jsonify({
            "total":    len(results),
            "success":  success_count,
            "skipped":  skip_count,
            "errors":   error_count,
            "results":  results,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  AUTO-REPLY SETTINGS
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/auto-reply/status", methods=["GET"])
def api_auto_reply_status():
    return jsonify({"enabled": is_auto_reply_enabled()})


@app.route("/api/auto-reply/toggle", methods=["POST"])
def api_auto_reply_toggle():
    data = request.get_json()
    enabled = data.get("enabled", False)
    set_setting("auto_reply_enabled", "true" if enabled else "false")
    return jsonify({"enabled": enabled, "message": f"Auto-reply {'enabled' if enabled else 'disabled'}"})


# ──────────────────────────────────────────────────────────────────────────
#  LOGS & STATS
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/logs", methods=["GET"])
def api_logs():
    try:
        return jsonify({"logs": get_all_logs()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    try:
        return jsonify(get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  DM ROUTES
# ──────────────────────────────────────────────────────────────────────────

@app.route("/api/dm/conversations", methods=["GET"])
def api_dm_conversations():
    try:
        return jsonify({"conversations": get_conversations()})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/messages", methods=["POST"])
def api_dm_messages():
    data = request.get_json()
    conversation_id = data.get("conversation_id", "").strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    try:
        return jsonify({"messages": get_conversation_messages(conversation_id)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/generate-reply", methods=["POST"])
def api_dm_generate_reply():
    data = request.get_json()
    message_text = data.get("message_text", "").strip()
    sender_name = data.get("sender_name", "")
    reel_url = data.get("reel_url", "")
    post_context = data.get("post_context", "")

    if reel_url and not post_context:
        try:
            ctx = get_reel_context_from_url(reel_url)
            post_context = ctx.get("summary", "")
        except Exception:
            post_context = f"User shared a reel: {reel_url}"

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
        save_dm_log(conversation_id=conversation_id, recipient_id=recipient_id,
                    sender_name=sender_name, message_text=message_text,
                    reply_text=reply_text, reel_url=reel_url,
                    ig_message_id=ig_resp.get("message_id", ""))
        return jsonify({"success": True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dm/logs", methods=["GET"])
def api_dm_logs():
    try:
        return jsonify({"logs": get_all_dm_logs()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────
#  WEBHOOK — handles comments + DMs, respects auto-reply toggle
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

                # ── Comment auto-reply ──
                if field == "comments":
                    if not is_auto_reply_enabled():
                        print(
                            "[Webhook] Comment received but auto-reply is OFF — skipping")
                        continue

                    comment_id = val.get("id")
                    comment_text = val.get("text", "")
                    commenter = val.get("from", {}).get("username", "user")
                    post_id = val.get("media", {}).get("id", "")

                    if not comment_id or not post_id:
                        continue

                    # Skip if already replied
                    if is_comment_already_replied(comment_id):
                        print(
                            f"[Webhook] Already replied to comment {comment_id} — skipping")
                        continue

                    ctx = get_post_context(post_id)
                    post_context = ctx.get("summary", "")
                    reply = generate_reply(
                        post_context, comment_text, commenter)
                    ig_resp = post_reply(comment_id, reply)
                    save_reply_log(post_id=post_id, comment_id=comment_id,
                                   commenter=commenter, comment_text=comment_text,
                                   reply_text=reply, post_context=post_context,
                                   ig_reply_id=ig_resp.get("id", ""))
                    print(
                        f"[Webhook] Auto-replied to @{commenter}: {reply[:60]}…")

                # ── DM auto-reply ──
                elif field == "messages":
                    for msg_event in val.get("messaging", []):
                        sender_id = msg_event.get("sender", {}).get("id", "")
                        sender_name = msg_event.get(
                            "sender", {}).get("name", "")
                        msg = msg_event.get("message", {})
                        msg_text = msg.get("text", "")

                        if sender_id == os.getenv("IG_USER_ID", ""):
                            continue

                        reel_url = ""
                        post_context = ""
                        for att in msg.get("attachments", []):
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
                        save_dm_log(conversation_id="", recipient_id=sender_id,
                                    sender_name=sender_name, message_text=display_text,
                                    reply_text=reply, reel_url=reel_url,
                                    ig_message_id=ig_resp.get("message_id", ""))

    except Exception:
        traceback.print_exc()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
