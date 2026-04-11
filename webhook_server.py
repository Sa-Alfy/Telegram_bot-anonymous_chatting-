# ═══════════════════════════════════════════════════════════════════════
# FILE: webhook_server.py
# PURPOSE: Flask web server — Messenger webhook + health endpoint
# STATUS: NEW FILE
# DEPENDENCIES: Flask, messenger_handlers.py, config.py
# ═══════════════════════════════════════════════════════════════════════

import logging
import time
from flask import Flask, jsonify, request

from config import PORT, MESSENGER_ENABLED
from state.match_state import match_state

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────
# Root / Info route
# ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    """Root endpoint — informational."""
    return jsonify({
        "service": "Anonymous Chat Bot",
        "platforms": ["Telegram", "Facebook Messenger"] if MESSENGER_ENABLED else ["Telegram"],
        "status": "running",
        "messenger_enabled": MESSENGER_ENABLED,
    }), 200


@app.route("/privacy", methods=["GET"])
def privacy():
    """Basic privacy policy for Facebook requirements."""
    return """
    <html>
        <head><title>Privacy Policy</title></head>
        <body>
            <h1>Privacy Policy</h1>
            <p>This Anonymous Chat Bot does not store your private Facebook data. 
            We only process messages to facilitate anonymous chats between users. 
            No message history is permanently stored in a way that identifies you.</p>
        </body>
    </html>
    """, 200


# ─────────────────────────────────────────────────────────────────────
# Health check (used by Render keep-alive ping and uptime monitors)
# ─────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint — returns bot stats as JSON."""
    uptime = int(time.time() - match_state.bot_start_time)
    hours, rem = divmod(uptime, 3600)
    minutes, seconds = divmod(rem, 60)

    return jsonify({
        "status": "healthy",
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "active_chats": len(match_state.active_chats) // 2,
        "queue_length": len(match_state.waiting_queue),
        "messenger_enabled": MESSENGER_ENABLED,
    }), 200


# ─────────────────────────────────────────────────────────────────────
# Facebook Messenger Webhook
# ─────────────────────────────────────────────────────────────────────

@app.before_request
def log_request_info():
    if "messenger" in request.path:
        logger.info(f"🌐 [INCOMING] {request.method} {request.path} | Args: {request.args.to_dict()}")

@app.route("/messenger-webhook", methods=["GET"])
@app.route("/messenger-webhook/", methods=["GET"])
def messenger_webhook_verify():
    """Facebook webhook verification (GET)."""
    if not MESSENGER_ENABLED:
        return "Messenger not configured.", 503
    from messenger_handlers import handle_messenger_webhook_get
    return handle_messenger_webhook_get()


@app.route("/messenger-webhook", methods=["POST"])
@app.route("/messenger-webhook/", methods=["POST"])
def messenger_webhook_receive():
    """Receive Messenger events (POST). Always returns 200 per FB requirements."""
    if not MESSENGER_ENABLED:
        return "ok", 200
    from messenger_handlers import handle_messenger_webhook_post
    return handle_messenger_webhook_post()


# ─────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500


def run_flask():
    """Start the Flask server (blocking). Call in main thread."""
    logger.info(f"🌐 Flask webhook server starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ═══════════════════════════════════════════════════════════════════════
# END OF webhook_server.py
# ═══════════════════════════════════════════════════════════════════════
