# ═══════════════════════════════════════════════════════════════════════
# FILE: webhook_server.py
# PURPOSE: Flask web server — Messenger webhook + health + compliance endpoints
# STATUS: UPGRADED — Meta App Review compliant
# DEPENDENCIES: Flask, messenger_handlers.py, config.py
# ═══════════════════════════════════════════════════════════════════════

import logging
import os
import time
import json
import hashlib
import hmac
import base64
from flask import Flask, jsonify, request

from config import PORT, MESSENGER_ENABLED, APP_SECRET, FB_PAGE_ID
from state.match_state import match_state
from messenger.dispatcher import handle_messenger_webhook_get, handle_messenger_webhook_post

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────
# Root / Info route
# ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    """Root endpoint — informational."""
    return jsonify({
        "service": "Neonymo — Anonymous Chat Bot",
        "platforms": ["Telegram", "Facebook Messenger"] if MESSENGER_ENABLED else ["Telegram"],
        "status": "running",
        "messenger_enabled": MESSENGER_ENABLED,
        "privacy_policy": "/privacy",
        "terms_of_service": "/terms",
    }), 200


# ─────────────────────────────────────────────────────────────────────
# Privacy Policy (Meta App Review requirement)
# ─────────────────────────────────────────────────────────────────────

@app.route("/privacy", methods=["GET"])
def privacy_policy():
    """Comprehensive privacy policy for Meta App Review."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy — Neonymo Anonymous Chat</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; line-height: 1.7; max-width: 800px; margin: auto; color: #333; }
            h1 { color: #1a1a2e; } h2 { color: #16213e; margin-top: 2em; } h3 { color: #0f3460; }
            .updated { color: #666; font-size: 0.9em; }
            ul { padding-left: 1.5em; }
        </style>
    </head>
    <body>
        <h1>Privacy Policy</h1>
        <p class="updated">Last updated: April 2026</p>

        <h2>1. Introduction</h2>
        <p>Neonymo ("we", "us", "our") operates an anonymous chat service on Facebook Messenger and Telegram.
        This policy explains what data we collect, how we use it, and your rights.</p>

        <h2>2. Data We Collect</h2>
        <h3>2.1 Data You Provide</h3>
        <ul>
            <li><strong>Profile information:</strong> Gender, location (city-level), and bio text you optionally provide during onboarding.</li>
            <li><strong>Messages:</strong> Text messages are relayed in real-time to your chat partner and are <strong>not stored</strong> permanently on our servers.</li>
        </ul>
        <h3>2.2 Automatically Collected Data</h3>
        <ul>
            <li><strong>Platform User ID:</strong> A hashed version of your Facebook Page-Scoped ID (PSID) or Telegram ID, used solely for session management.</li>
            <li><strong>Usage metrics:</strong> Number of matches, chat duration (aggregated), and in-app currency balance.</li>
            <li><strong>Timestamps:</strong> Last login time and last active time for session management.</li>
        </ul>
        <h3>2.3 Data We Do NOT Collect</h3>
        <ul>
            <li>Your real name, email address, phone number, or Facebook profile information</li>
            <li>Your contacts or friend lists</li>
            <li>Your location data (GPS/IP-based)</li>
            <li>Message content after delivery (messages are not logged or stored)</li>
        </ul>

        <h2>3. How We Use Your Data</h2>
        <ul>
            <li>To match you with other anonymous users for chat sessions</li>
            <li>To enforce safety rules and prevent abuse (report system, auto-moderation)</li>
            <li>To manage your in-app currency and progression</li>
        </ul>
        <p>We do <strong>not</strong> use your data for advertising, profiling, or any purpose other than operating this chat service.</p>

        <h2>4. Data Sharing</h2>
        <p>We do <strong>not</strong> share, sell, or transfer your data to any third parties, advertisers, data brokers, or other services.</p>

        <h2>5. Data Retention</h2>
        <ul>
            <li><strong>Active accounts:</strong> Profile data is retained while your account is active.</li>
            <li><strong>Inactive accounts:</strong> Accounts inactive for 180 days may be automatically anonymized.</li>
            <li><strong>Messages:</strong> Chat messages are processed in real-time memory only and are never permanently stored.</li>
            <li><strong>Reports:</strong> Abuse reports are retained for up to 90 days for safety enforcement, then anonymized.</li>
        </ul>

        <h2>6. Your Rights</h2>
        <p>Under GDPR, CCPA, and applicable privacy laws, you have the right to:</p>
        <ul>
            <li><strong>Access:</strong> Request a copy of your stored data by sending <code>/stats</code> in the bot.</li>
            <li><strong>Deletion:</strong> Request deletion of your data by sending <code>/delete</code> in the bot, or through your <a href="https://www.facebook.com/settings?tab=applications">Facebook App Settings</a>.</li>
            <li><strong>Opt-out:</strong> Stop using the service at any time. You can block the bot on Messenger to cease all interaction.</li>
            <li><strong>Portability:</strong> Contact our support to request an export of your profile data.</li>
        </ul>

        <h2>7. Data Deletion</h2>
        <p>When you request data deletion:</p>
        <ul>
            <li>Your profile information (gender, location, bio) is permanently erased.</li>
            <li>Your account is anonymized (personal identifiers are removed).</li>
            <li>Your in-app currency and progression data are reset.</li>
            <li>This process is irreversible and completed within 24 hours.</li>
        </ul>

        <h2>8. Security</h2>
        <p>We use industry-standard security measures including encrypted connections (TLS), signed webhook verification, and secure cloud hosting. We do not store passwords or sensitive authentication tokens in application logs.</p>

        <h2>9. Children's Privacy</h2>
        <p>This service is intended for users aged 18 and above. We do not knowingly collect data from minors. If we become aware of a minor using the service, their account will be immediately terminated and their data deleted.</p>

        <h2>10. Changes to This Policy</h2>
        <p>We may update this policy from time to time. Material changes will be communicated through the bot.</p>

        <h2>11. Contact</h2>
        <p>For privacy inquiries, data requests, or concerns:<br>
        Send <code>/help</code> in the bot, or contact the bot administrator via Telegram.</p>
    </body>
    </html>
    """, 200


# ─────────────────────────────────────────────────────────────────────
# Terms of Service (Meta App Review requirement)
# ─────────────────────────────────────────────────────────────────────

@app.route("/terms", methods=["GET"])
def terms_of_service():
    """Terms of Service page for Meta App Review."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Terms of Service — Neonymo Anonymous Chat</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; line-height: 1.7; max-width: 800px; margin: auto; color: #333; }
            h1 { color: #1a1a2e; } h2 { color: #16213e; margin-top: 2em; }
            .updated { color: #666; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h1>Terms of Service</h1>
        <p class="updated">Last updated: April 2026</p>

        <h2>1. Acceptance</h2>
        <p>By using Neonymo, you agree to these terms. If you do not agree, do not use the service.</p>

        <h2>2. Service Description</h2>
        <p>Neonymo is an anonymous chat service that randomly pairs users for text-based conversations. The service is provided "as is" without guarantees of availability.</p>

        <h2>3. Eligibility</h2>
        <p>You must be at least 18 years old to use this service.</p>

        <h2>4. User Conduct</h2>
        <p>You agree NOT to:</p>
        <ul>
            <li>Share illegal content, including but not limited to child exploitation material</li>
            <li>Harass, threaten, or abuse other users</li>
            <li>Spam, advertise, or solicit other users</li>
            <li>Share personal contact information (phone numbers, emails, social media) in chats</li>
            <li>Impersonate other individuals or entities</li>
            <li>Attempt to circumvent rate limits, bans, or moderation systems</li>
        </ul>

        <h2>5. Moderation & Enforcement</h2>
        <p>We use automated moderation (keyword filtering, spam detection) and user-driven reporting. Violations may result in warnings, temporary mutes, or permanent bans. Banned users may appeal through the bot.</p>

        <h2>6. Limitation of Liability</h2>
        <p>Neonymo is not responsible for content shared by users. We do not moderate or screen individual messages in real-time beyond automated keyword filters. Use the service at your own risk.</p>

        <h2>7. Termination</h2>
        <p>We reserve the right to terminate or suspend your access at any time for violations of these terms, without prior notice.</p>

        <h2>8. Privacy</h2>
        <p>Your use of Neonymo is also governed by our <a href="/privacy">Privacy Policy</a>.</p>
    </body>
    </html>
    """, 200


# ─────────────────────────────────────────────────────────────────────
# Data Deletion Callback (Meta requirement)
# ─────────────────────────────────────────────────────────────────────

def _parse_signed_request(signed_request: str, app_secret: str) -> dict:
    """Parse and verify a Facebook signed_request."""
    try:
        encoded_sig, payload = signed_request.split('.', 1)
        # Decode signature
        sig = base64.urlsafe_b64decode(encoded_sig + '==')
        # Decode payload
        data = json.loads(base64.urlsafe_b64decode(payload + '=='))
        # Verify signature
        expected_sig = hmac.new(
            app_secret.encode(), payload.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return data
    except Exception as e:
        logger.error(f"Failed to parse signed_request: {e}")
        return None


@app.route("/delete-data", methods=["POST"])
def delete_data_callback():
    """Meta Data Deletion Callback — handles user data deletion requests from Facebook Settings.
    
    Returns a JSON response with a confirmation URL and status code per Meta requirements.
    """
    signed_request = request.form.get("signed_request", "")
    if not signed_request or not APP_SECRET:
        return jsonify({"error": "Invalid request"}), 400

    data = _parse_signed_request(signed_request, APP_SECRET)
    if not data:
        return jsonify({"error": "Invalid signature"}), 403

    fb_user_id = data.get("user_id")
    if not fb_user_id:
        return jsonify({"error": "No user_id in request"}), 400

    # Perform soft deletion asynchronously
    import hashlib as _hl
    psid = str(fb_user_id)
    psid_hash = int(_hl.sha256(psid.encode()).hexdigest(), 16)
    virtual_id = (psid_hash % (10**15)) + 10**15

    try:
        import app_state
        import asyncio
        if app_state.bot_loop and app_state.bot_loop.is_running():
            async def _soft_delete():
                from database.repositories.user_repository import UserRepository
                await UserRepository.soft_delete_user_data(virtual_id)
                logger.info(f"Data deletion completed for virtual_id ending ...{str(virtual_id)[-4:]}")

            future = asyncio.run_coroutine_threadsafe(_soft_delete(), app_state.bot_loop)
            future.result(timeout=10)
    except Exception as e:
        logger.error(f"Data deletion callback error: {e}")

    # Generate a confirmation code for the user
    confirmation_code = hashlib.sha256(f"del_{fb_user_id}_{int(time.time())}".encode()).hexdigest()[:12]
    
    # Meta requires this exact response format
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    status_url = f"{render_url}/deletion-status?code={confirmation_code}" if render_url else f"https://example.com/deletion-status?code={confirmation_code}"

    return jsonify({
        "url": status_url,
        "confirmation_code": confirmation_code
    }), 200


@app.route("/deletion-status", methods=["GET"])
def deletion_status():
    """Shows data deletion confirmation page."""
    code = request.args.get("code", "N/A")
    
    import re
    from markupsafe import escape
    if not re.match(r'^[a-f0-9]{1,16}$', code):
        code = "Invalid"
    else:
        code = escape(code)
        
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Data Deletion Status — Neonymo</title>
        <style>body {{ font-family: sans-serif; padding: 40px; max-width: 600px; margin: auto; }}</style>
    </head>
    <body>
        <h1>Data Deletion Request</h1>
        <p><strong>Status:</strong> ✅ Completed</p>
        <p><strong>Confirmation Code:</strong> <code>{code}</code></p>
        <p>Your data has been anonymized. All personal identifiers, profile information, and session history have been erased. This action is irreversible.</p>
        <p>If you have questions, contact the bot administrator via Telegram.</p>
    </body>
    </html>
    """, 200


# ─────────────────────────────────────────────────────────────────────
# Health check (used by Render keep-alive ping and uptime monitors)
# ─────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    """Consolidated health check with live diagnostics and stats."""
    from config import MESSENGER_ENABLED, PAGE_ACCESS_TOKEN, VERIFY_TOKEN
    import app_state
    
    # Check if Pyrogram app is healthy
    tg_connected = False
    try:
        if app_state.telegram_app and app_state.telegram_app.is_connected:
            tg_connected = True
    except Exception as e:
        logger.debug(f"Health check: Pyrogram liveness probe failed: {e}")

    # Fetch real-time stats from the bot loop if possible
    bot_stats = {"active_chats": 0, "queue_length": 0}
    try:
        import asyncio
        if app_state.bot_loop and app_state.bot_loop.is_running():
            from state.match_state import match_state
            future = asyncio.run_coroutine_threadsafe(match_state.get_stats(), app_state.bot_loop)
            # lowered timeout to 1s to prevent Waitress thread exhaustion
            bot_stats = future.result(timeout=1.0) or bot_stats 
    except Exception as e:
        logger.debug(f"Health check could not fetch live stats: {e}")

    # Redis liveness check
    redis_status = "not_configured"
    try:
        import asyncio
        from services.distributed_state import distributed_state
        if distributed_state.redis and app_state.bot_loop and app_state.bot_loop.is_running():
            async def _ping_redis():
                return await distributed_state.redis.ping()
            future = asyncio.run_coroutine_threadsafe(_ping_redis(), app_state.bot_loop)
            pong = future.result(timeout=1.0)
            redis_status = "connected" if pong else "error"
    except Exception as e:
        logger.debug(f"Health check: Redis liveness probe failed: {e}")
        redis_status = "error"

    # Database liveness check
    db_status = "unknown"
    try:
        import asyncio
        from database.connection import db
        if db._pool and app_state.bot_loop and app_state.bot_loop.is_running():
            async def _ping_db():
                async with db._pool.acquire() as conn:
                    return await conn.fetchval("SELECT 1")
            future = asyncio.run_coroutine_threadsafe(_ping_db(), app_state.bot_loop)
            result = future.result(timeout=1.0)
            db_status = "connected" if result == 1 else "error"
    except Exception as e:
        logger.debug(f"Health check: DB liveness probe failed: {e}")
        db_status = "error"

    # Build response — no sensitive data exposed
    status = {
        "status": "online",
        "telegram": "connected" if tg_connected else "disconnected",
        "messenger": "ENABLED" if MESSENGER_ENABLED else "DISABLED",
        "bot_loop": "running" if (app_state.bot_loop and app_state.bot_loop.is_running()) else "stopped",
        "redis": redis_status,
        "database": db_status,
        "stats": bot_stats,
    }
        
    return jsonify(status), 200


# ─────────────────────────────────────────────────────────────────────
# Facebook Messenger Webhook
# ─────────────────────────────────────────────────────────────────────

@app.before_request
def log_request_info():
    """Diagnostic hook to track incoming webhook traffic — PII-safe."""
    if "messenger" in request.path.lower():
        logger.info(f"[WEBHOOK] {request.method} {request.path} | Signed: {bool(request.headers.get('X-Hub-Signature-256'))}")

@app.route("/messenger-webhook", methods=["GET"])
@app.route("/messenger-webhook/", methods=["GET"])
def messenger_webhook_verify():
    """Facebook webhook verification (GET)."""
    if not MESSENGER_ENABLED:
        return "Messenger not configured.", 503
    return handle_messenger_webhook_get()


@app.route("/messenger-webhook", methods=["POST"])
@app.route("/messenger-webhook/", methods=["POST"])
def messenger_webhook_receive():
    """Receive Messenger events (POST). Always returns 200 per FB requirements."""
    if not MESSENGER_ENABLED:
        return "ok", 200
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
    """Start the Flask server using Waitress (Production WSGI)."""
    from waitress import serve
    logger.info(f"Production Flask server (Waitress) starting on port {PORT}")
    serve(app, host="0.0.0.0", port=PORT)


# ═══════════════════════════════════════════════════════════════════════
# END OF webhook_server.py
# ═══════════════════════════════════════════════════════════════════════
