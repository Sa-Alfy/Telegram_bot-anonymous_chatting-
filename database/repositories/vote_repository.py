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
            logger.error(f"Error fetching vote: {e}", exc_info=True)
            return None

    @staticmethod
    async def submit_vote(voter_id: int, voted_id: int, vote_type: Optional[str] = None, gender_vote: Optional[str] = None) -> bool:
        """Submit a rating (like/dislike) and/or gender (male/female) vote."""
        now = int(time.time())
        try:
            # 1. Fetch existing partially safe (handle missing gender_vote column)
            existing = None
            try:
                existing = await db.fetchone(
                    "SELECT vote_type, gender_vote FROM user_votes WHERE voter_id = $1 AND voted_id = $2",
                    (voter_id, voted_id)
                )
            except Exception:
                try:
                    existing = await db.fetchone(
                        "SELECT vote_type FROM user_votes WHERE voter_id = $1 AND voted_id = $2",
                        (voter_id, voted_id)
                    )
                except Exception as e_sel:
                    logger.debug(f"Vote fetch fail (likely fresh): {e_sel}")

            new_vote_type = vote_type if vote_type is not None else (existing['vote_type'] if existing and 'vote_type' in existing else None)
            
            # Check if gender_vote column exists in existing record if we have one
            has_gender_col = existing and 'gender_vote' in existing
            new_gender_vote = gender_vote if gender_vote is not None else (existing['gender_vote'] if has_gender_col else None)
            
            # 2. Attempt Full Insert/Update
            try:
                await db.execute("""
                    INSERT INTO user_votes (voter_id, voted_id, vote_type, gender_vote, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (voter_id, voted_id) 
                    DO UPDATE SET vote_type = EXCLUDED.vote_type, gender_vote = EXCLUDED.gender_vote
                """, (voter_id, voted_id, new_vote_type, new_gender_vote, now))
            except Exception as e_ins:
                logger.warning(f"Full vote insert failed, trying fallback: {e_ins}")
                # Fallback: update only vote_type (ignore gender_vote if column missing)
                await db.execute("""
                    INSERT INTO user_votes (voter_id, voted_id, vote_type, created_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (voter_id, voted_id) 
                    DO UPDATE SET vote_type = EXCLUDED.vote_type
                """, (voter_id, voted_id, new_vote_type, now))
            
            # 3. Recalculate aggregates
            await VoteRepository._recalculate_voter_stats(voter_id)
            await VoteRepository._recalculate_aggregates(voted_id)
            return True
        except Exception as e:
            logger.error(f"Error submitting vote from {voter_id} to {voted_id}: {e}", exc_info=True)
            return False

    @staticmethod
    async def _recalculate_aggregates(user_id: int):
        """Recalculate likes, dislikes, and gender votes for a user.
        Fault-tolerant: missing columns will not fail the vote itself.
        """
        try:
            stats = await db.fetchone("""
                SELECT 
                    COUNT(*) FILTER (WHERE uv.vote_type = 'like') as likes_cnt,
                    COUNT(*) FILTER (WHERE uv.vote_type = 'dislike') as dislikes_cnt,
                    COUNT(*) FILTER (WHERE uv.gender_vote = 'male') as male_cnt,
                    COUNT(*) FILTER (WHERE uv.gender_vote = 'female') as female_cnt
                FROM user_votes uv
                LEFT JOIN users voter ON uv.voter_id = voter.telegram_id
                WHERE uv.voted_id = $1
                AND (
                    (COALESCE(voter.given_likes, 0) + COALESCE(voter.given_dislikes, 0) < 10) OR
                    (CAST(COALESCE(voter.given_dislikes, 0) AS FLOAT) / (COALESCE(voter.given_likes, 0) + COALESCE(voter.given_dislikes, 0)) <= 0.8)
                )
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

            # Only update columns we're confident exist.
            # votes_male/votes_female/verified_gender are optional schema columns.
            try:
                await db.execute("""
                    UPDATE users 
                    SET likes = $1, dislikes = $2, votes_male = $3, votes_female = $4, verified_gender = $5
                    WHERE telegram_id = $6
                """, (likes_cnt, dislikes_cnt, male_cnt, female_cnt, verified_gender, user_id))
            except Exception:
                # Fallback: update only the guaranteed-to-exist likes/dislikes columns
                try:
                    await db.execute("""
                        UPDATE users SET likes = $1, dislikes = $2 WHERE telegram_id = $3
                    """, (likes_cnt, dislikes_cnt, user_id))
                except Exception as e2:
                    logger.warning(f"Aggregate fallback update also failed for {user_id}: {e2}")
        except Exception as e:
            logger.warning(f"_recalculate_aggregates failed for {user_id}: {e}")

    @staticmethod
    async def _recalculate_voter_stats(voter_id: int):
        """Recalculate given_likes and given_dislikes for a user."""
        try:
            stats = await db.fetchone("""
                SELECT 
                    COUNT(*) FILTER (WHERE vote_type = 'like') as given_likes_cnt,
                    COUNT(*) FILTER (WHERE vote_type = 'dislike') as given_dislikes_cnt
                FROM user_votes
                WHERE voter_id = $1
            """, (voter_id,))
            if not stats: return
            
            gl_cnt = stats['given_likes_cnt'] or 0
            gd_cnt = stats['given_dislikes_cnt'] or 0
            
            try:
                await db.execute("""
                    UPDATE users 
                    SET given_likes = $1, given_dislikes = $2
                    WHERE telegram_id = $3
                """, (gl_cnt, gd_cnt, voter_id))
            except Exception as e:
                logger.warning(f"Voter stats update failed for {voter_id}: {e}")
        except Exception as e:
            logger.warning(f"_recalculate_voter_stats failed for {voter_id}: {e}")
