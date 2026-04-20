# adapters/messenger/ui_factory.py

def get_messenger_home_buttons():
    return [
        {"title": "🔍 Find Partner", "payload": "START_SEARCH"},
        {"title": "👤 Profile",     "payload": "CMD_PROFILE"},
        {"title": "📊 Stats",       "payload": "STATS"}
    ]

def get_messenger_chat_buttons(match_id: str):
    """Guided UX: Only Primary actions visible."""
    return [
        {"title": "⏭️ Next Chat", "payload": f"NEXT_MATCH:{match_id}"},
        {"title": "🛑 End Chat",  "payload": f"END_CHAT:{match_id}"},
        {"title": "🛠 Tools",      "payload": f"TOOLS_MENU:{match_id}"}
    ]

def get_messenger_tools_buttons(match_id: str):
    """Hidden secondary actions."""
    return [
        {"title": "🧊 Icebreaker", "payload": f"ICEBREAKER:{match_id}"},
        {"title": "🔓 Reveal",      "payload": f"REVEAL:{match_id}"},
        {"title": "🚩 Report",      "payload": f"REPORT:{match_id}"}
    ]

def get_messenger_vote_card(match_id: str, signal: str):
    if signal == "reputation":
        return {
            "title": "🗳 Reputation Vote",
            "subtitle": "How was your partner?",
            "buttons": [
                {"type": "postback", "title": "👍 Good", "payload": f"VOTE:reputation:good:{match_id}"},
                {"type": "postback", "title": "👎 Bad",  "payload": f"VOTE:reputation:bad:{match_id}"}
            ]
        }
    elif signal == "identity":
        return {
            "title": "🗳 Identity Vote",
            "subtitle": "What was their gender?",
            "buttons": [
                {"type": "postback", "title": "👨 Male",   "payload": f"VOTE:identity:male:{match_id}"},
                {"type": "postback", "title": "👩 Female", "payload": f"VOTE:identity:female:{match_id}"},
                {"type": "postback", "title": "❓ Unsure", "payload": f"VOTE:identity:unsure:{match_id}"}
            ]
        }
    return None
