import asyncio
from typing import Dict, Any, Tuple
from pyrogram import Client, types
from database.repositories.vote_repository import VoteRepository

class VotingHandler:
    @staticmethod
    async def handle_vote(client: Client, user_id: int, target_id: int, vote: str) -> Dict[str, Any]:
        """
        Process a vote from voter (user_id) for target (target_id).
        Vote string format expected: 'like', 'dislike', 'gender_male', 'gender_female'
        """
        from utils.logger import logger
        logger.info(f"VOTE ATTEMPT: voter={user_id}, target={target_id}, vote_str='{vote}'")
        if user_id == target_id:
            return {"alert": "❌ You cannot vote for yourself!", "show_alert": True}
            
        vote_type = None
        gender_vote = None
        if vote in ("like", "dislike"):
            vote_type = vote
        elif vote in ("gender_male", "gender_female"):
            gender_vote = "male" if vote == "gender_male" else "female"
            
        success = await VoteRepository.submit_vote(
            voter_id=user_id, 
            voted_id=target_id, 
            vote_type=vote_type, 
            gender_vote=gender_vote
        )
        
        if success:
            msg = "✅ Vote recorded!"
            if gender_vote:
                msg = f"✅ Thanks for voting! You verified them as {'👨 Male' if gender_vote == 'male' else '👩 Female'}."
            elif vote_type == "like":
                msg = "👍 You liked this user!"
            elif vote_type == "dislike":
                msg = "👎 You disliked this user."
            return {"alert": msg, "show_alert": False}
        else:
            return {"alert": "❌ Failed to record vote. Please try again later.", "show_alert": True}

