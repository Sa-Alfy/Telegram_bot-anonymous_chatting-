"""
Content filter module — regex-based moderation for Meta compliance.
Upgraded with normalization, behavior-aware escalation, and multi-pattern scanning.
"""

import re
import logging
import unicodedata
import time
from typing import Tuple, Optional, Dict, List, Any

# Severity levels
SEVERITY_WARN = "warn"         # Message blocked, user warned
SEVERITY_BLOCK = "block"       # Message blocked + chat terminated
SEVERITY_AUTO_BAN = "auto_ban" # Message blocked + chat terminated + auto-ban

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Pattern definitions: (compiled_regex, severity, category, description)
# ─────────────────────────────────────────────────────────────────────
_PATTERNS = [
    # CRITICAL — auto-ban triggers
    (re.compile(r'\bchild\s*porn', re.IGNORECASE), SEVERITY_AUTO_BAN, "csam", "CSAM content"),
    (re.compile(r'\bunderage\b.*\b(sex|nude|naked)', re.IGNORECASE), SEVERITY_AUTO_BAN, "minor_exploitation", "Minor exploitation"),

    # HIGH — block + disconnect
    (re.compile(r't\.me/(joinchat|\+)', re.IGNORECASE), SEVERITY_BLOCK, "telegram_spam", "Telegram invite spam"),
    (re.compile(r'onlyfans\.com', re.IGNORECASE), SEVERITY_BLOCK, "adult_promotion", "Adult content promotion"),
    (re.compile(r'bitcoin\s*double', re.IGNORECASE), SEVERITY_BLOCK, "scam", "Crypto scam"),
    (re.compile(r'\b(buy|sell)\s*(drugs|weed|coke|meth|heroin)', re.IGNORECASE), SEVERITY_BLOCK, "illegal_goods", "Drug dealing"),
    (re.compile(r'(bit\.ly|tinyurl|shorturl|adf\.ly)/\S+', re.IGNORECASE), SEVERITY_BLOCK, "suspicious_link", "Suspicious short URL"),
    (re.compile(r'\b(kill\s*(yourself|urself|ur\s*self)|kys)\b', re.IGNORECASE), SEVERITY_BLOCK, "self_harm", "Self-harm incitement"),

    # MEDIUM — warn + block message
    (re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE), SEVERITY_WARN, "url_sharing", "URL sharing"),
    (re.compile(r'\b\d{7,15}\b', re.IGNORECASE), SEVERITY_WARN, "contact_sharing", "Phone number sharing"),
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', re.IGNORECASE), SEVERITY_WARN, "contact_sharing", "Email sharing"),
    (re.compile(r'@\w{3,}', re.IGNORECASE), SEVERITY_WARN, "contact_sharing", "Social media handle sharing"),
    (re.compile(r'\b(whatsapp|telegram|snapchat|instagram|facebook|discord)\b.*\b(add|dm|message|contact)\b', re.IGNORECASE), SEVERITY_WARN, "contact_sharing", "Contact exchange attempt"),
]

_URL_WHITELIST = {"meet.jit.si"}
_FAST_PATH_KEYWORDS = {"porn", "sex", "nude", "naked", "bitcoin", "drugs", "kill", "kys", "add", "dm", "whatsapp", "telegram"}

def normalize_text(text: str) -> str:
    """Normalize text to prevent evasion."""
    if not text: return ""
    text = unicodedata.normalize('NFKC', text)
    text = "".join(ch for ch in text if ch not in {'\u200b', '\u200c', '\u200d', '\ufeff'})
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _is_suspicious_fast(text: str) -> bool:
    """Fast check to skip expensive regex scan."""
    if any(c in text for c in ('.', '/', '@')): return True
    if any(c.isdigit() for c in text): return True
    for kw in _FAST_PATH_KEYWORDS:
        if kw in text: return True
    return False

def check_message(text: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check a message against all content filters.
    Returns: (is_safe, violation_obj or None)
    """
    if not text:
        return True, None

    # Step 4: Fast path optimization
    text_lower = text.lower()
    if not _is_suspicious_fast(text_lower):
        return True, None

    # Step 1: Normalize
    normalized = normalize_text(text)
    
    # Step 3: Scan all patterns and select highest severity
    highest_violation = None
    severity_rank = {SEVERITY_AUTO_BAN: 3, SEVERITY_BLOCK: 2, SEVERITY_WARN: 1}

    for pattern, severity, category, description in _PATTERNS:
        # Scan BOTH original and normalized for maximum coverage
        match = pattern.search(text) or pattern.search(normalized)
        if match:
            matched_text = match.group(0)

            # Whitelist checks
            if category in ("url_sharing", "suspicious_link"):
                if any(domain in matched_text.lower() for domain in _URL_WHITELIST):
                    continue
            if category == "contact_sharing" and "Phone number" in description:
                if len(re.sub(r'\D', '', matched_text)) < 7:
                    continue

            current_violation = {
                "severity": severity,
                "category": category,
                "description": description,
                "matched_text": matched_text
            }

            if not highest_violation or severity_rank[severity] > severity_rank[highest_violation["severity"]]:
                highest_violation = current_violation

    if highest_violation:
        logger.debug(f"Content filter triggered: {highest_violation['description']} (severity={highest_violation['severity']})")
        return False, highest_violation

    return True, None

async def apply_enforcement(user_id: int, violation: Dict[str, Any]) -> Dict[str, Any]:
    """Adjust severity based on user behavior and category overrides."""
    from utils.behavior_tracker import behavior_tracker
    
    severity = violation["severity"]
    category = violation["category"]
    
    # Step 5 & 6: Fetch Behavior and Decide
    signals = await behavior_tracker.get_signals(user_id)
    v_count = getattr(signals, 'violation_count', 0)

    # Escalation: 3+ -> upgrade warn to block; 5+ -> upgrade block to auto_ban
    if v_count >= 5 and severity == SEVERITY_BLOCK:
        severity = SEVERITY_AUTO_BAN
    elif v_count >= 3 and severity == SEVERITY_WARN:
        severity = SEVERITY_BLOCK

    # Category overrides
    if category in ("csam", "minor_exploitation"):
        severity = SEVERITY_AUTO_BAN
    elif category == "self_harm":
        severity = SEVERITY_BLOCK

    # Step 5: Update behavior tracker
    await behavior_tracker.record_violation(user_id)

    # Step 7: Economy Integration
    # Deductions: warn -> -10, block -> -25, auto_ban -> -100
    penalty_map = {SEVERITY_WARN: 10, SEVERITY_BLOCK: 25, SEVERITY_AUTO_BAN: 100}
    penalty = penalty_map.get(severity, 0)
    
    # Step 8: Define implementation response
    # warn: block message only
    # block: block message, terminate chat
    # auto_ban: block message, terminate chat, flag for ban
    action = "block_message"
    if severity in (SEVERITY_BLOCK, SEVERITY_AUTO_BAN):
        action = "terminate_chat"
    if severity == SEVERITY_AUTO_BAN:
        action = "auto_ban_user"

    # Step 9: Logging (Lightweight)
    logger.warning(f"ENFORCEMENT: uid={user_id} sev={severity} cat={category} match='{violation['matched_text']}'")

    return {
        "final_severity": severity,
        "action": action,
        "penalty": penalty,
        "description": violation["description"]
    }

def get_user_warning(severity: str, description: str, penalty: int = 0) -> str:
    """Generate a user-facing warning message."""
    if severity == SEVERITY_AUTO_BAN:
        return "🚫 **Auto-Moderator:** Your message violated critical safety guidelines. Your account has been flagged for review."
    elif severity == SEVERITY_BLOCK:
        return f"🚫 **Auto-Moderator:** Your message was blocked ({description}). Your chat has been terminated."
    else:
        p_text = f"\n\n💰 **Penalty:** {penalty} coins have been deducted." if penalty > 0 else ""
        return f"⚠️ **Safety Filter:** Your message was blocked — {description} is not allowed.{p_text}"
