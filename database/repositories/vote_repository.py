import time
from typing import Optional, Dict
from database.connection import db
from utils.logger import logger

class VoteRepository:
    @staticmethod
    async def get_vote(voter_id: int, voted_id: int) -> Optional[Dict]:
        """Check if a voter has already voted for this user."""
        try:
            record = await db.fetchone(
                "SELECT * FROM user_votes WHERE voter_id = $1 AND voted_id = $2",
                (voter_id, voted_id)
            )
            return dict(record) if record else None
        except Exception as e:
            logger.error(f"Error fetching vote: {e}")
            return None

    @staticmethod
    async def submit_vote(voter_id: int, voted_id: int, vote_type: Optional[str] = None, gender_vote: Optional[str] = None) -> bool:
        """Submit a rating (like/dislike) and/or gender (male/female) vote."""
        now = int(time.time())
        try:
            # Check existing to preserve partial votes
            existing = await db.fetchone(
                "SELECT vote_type, gender_vote FROM user_votes WHERE voter_id = $1 AND voted_id = $2",
                (voter_id, voted_id)
            )
            
            new_vote_type = vote_type if vote_type is not None else (existing['vote_type'] if existing else None)
            new_gender_vote = gender_vote if gender_vote is not None else (existing['gender_vote'] if existing else None)
            
            await db.execute("""
                INSERT INTO user_votes (voter_id, voted_id, vote_type, gender_vote, created_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (voter_id, voted_id) 
                DO UPDATE SET vote_type = EXCLUDED.vote_type, gender_vote = EXCLUDED.gender_vote
            """, (voter_id, voted_id, new_vote_type, new_gender_vote, now))
            
            # Recalculate aggregates
            await VoteRepository._recalculate_aggregates(voted_id)
            return True
        except Exception as e:
            logger.error(f"Error submitting vote: {e}")
            return False

    @staticmethod
    async def _recalculate_aggregates(user_id: int):
        """Recalculate likes, dislikes, and gender votes for a user."""
        stats = await db.fetchone("""
            SELECT 
                COUNT(*) FILTER (WHERE vote_type = 'like') as likes_cnt,
                COUNT(*) FILTER (WHERE vote_type = 'dislike') as dislikes_cnt,
                COUNT(*) FILTER (WHERE gender_vote = 'male') as male_cnt,
                COUNT(*) FILTER (WHERE gender_vote = 'female') as female_cnt
            FROM user_votes
            WHERE voted_id = $1
        """, (user_id,))
        
        if not stats:
            return
            
        likes_cnt = stats['likes_cnt'] or 0
        dislikes_cnt = stats['dislikes_cnt'] or 0
        male_cnt = stats['male_cnt'] or 0
        female_cnt = stats['female_cnt'] or 0
        
        # Determine verified gender. Need at least 5 votes, and > 80% consensus.
        verified_gender = None
        total_gender_votes = male_cnt + female_cnt
        if total_gender_votes >= 5:
            if male_cnt / total_gender_votes >= 0.8:
                verified_gender = 'male'
            elif female_cnt / total_gender_votes >= 0.8:
                verified_gender = 'female'
                
        await db.execute("""
            UPDATE users 
            SET likes = $1, dislikes = $2, votes_male = $3, votes_female = $4, verified_gender = $5
            WHERE telegram_id = $6
        """, (likes_cnt, dislikes_cnt, male_cnt, female_cnt, verified_gender, user_id))

