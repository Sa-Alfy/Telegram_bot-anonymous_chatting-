from pyngrok import ngrok
from config import NGROK_AUTHTOKEN, PORT
import os
import logging

logger = logging.getLogger(__name__)

def start_ngrok_tunnel():
    """Starts an ngrok tunnel on the configured PORT and returns the public URL."""
    if not NGROK_AUTHTOKEN:
        logger.error("❌ NGROK_AUTHTOKEN is missing. Cannot start tunnel.")
        return None

    try:
        # Set the authtoken
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
        
        # Start the tunnel
        logger.info(f"Starting ngrok tunnel on port {PORT}...")
        public_url = ngrok.connect(PORT).public_url
        
        # Canonicalize the URL (remove trailing slash and ensure https)
        public_url = public_url.replace("http://", "https://").rstrip("/")
        
        logger.info(f"Ngrok tunnel active: {public_url}")
        
        # Update the environment variable so other components (like setup_messenger) see it
        os.environ["RENDER_EXTERNAL_URL"] = public_url
        
        return public_url
    except Exception as e:
        logger.error(f"❌ Failed to start ngrok tunnel: {e}")
        return None

def stop_ngrok_tunnel():
    """Stops all active ngrok tunnels."""
    try:
        # Stop all tunnels
        ngrok.kill()
        logger.info("🔌 Ngrok tunnel stopped.")
    except Exception as e:
        logger.error(f"❌ Error stopping ngrok: {e}")
