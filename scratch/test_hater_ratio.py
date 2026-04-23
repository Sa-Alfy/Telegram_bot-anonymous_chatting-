import asyncio
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# Add root to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.connection import db
from database.repositories.user_repository import UserRepository
from database.repositories.vote_repository import VoteRepository

async def run_test():
    await db.connect()
    
    # 1. Setup mock users
    voted_id = 99991
    hater_id = 99992
    normal_id = 99993
    
    await db.execute("DELETE FROM user_votes WHERE voted_id = $1 OR voter_id = $1", (voted_id,))
    await db.execute("DELETE FROM user_votes WHERE voter_id = $1 OR voter_id = $2", (hater_id, normal_id))
    
    await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (voted_id,))
    await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (hater_id,))
    await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (normal_id,))
    
    # Hater: 15 dislikes
    for i in range(15):
        await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (1000 + i,))
        await db.execute("INSERT INTO user_votes (voter_id, voted_id, vote_type, created_at) VALUES ($1, $2, 'dislike', 0) ON CONFLICT DO NOTHING", (hater_id, 1000 + i))
    
    # Normal: 10 likes, 2 dislikes
    for i in range(10):
        await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (2000 + i,))
        await db.execute("INSERT INTO user_votes (voter_id, voted_id, vote_type, created_at) VALUES ($1, $2, 'like', 0) ON CONFLICT DO NOTHING", (normal_id, 2000 + i))
    for i in range(2):
        await db.execute("INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING", (3000 + i,))
        await db.execute("INSERT INTO user_votes (voter_id, voted_id, vote_type, created_at) VALUES ($1, $2, 'dislike', 0) ON CONFLICT DO NOTHING", (normal_id, 3000 + i))
    
    print("Users initialized.")
    
    # 2. Insert votes
    # Normal user likes
    await VoteRepository.submit_vote(voter_id=normal_id, voted_id=voted_id, vote_type="like")
    print("Normal user voted LIKE.")
    
    # Hater dislikes
    await VoteRepository.submit_vote(voter_id=hater_id, voted_id=voted_id, vote_type="dislike")
    print("Hater user voted DISLIKE.")
    
    # 3. Check stats
    user = await UserRepository.get_by_telegram_id(voted_id)
    likes = user.get("likes")
    dislikes = user.get("dislikes")
    
    print(f"Target User Stats: Likes={likes}, Dislikes={dislikes}")
    
    # Expected: Likes=1, Dislikes=0 (Hater's vote is ghosted!)
    assert likes == 1, f"Expected 1 like, got {likes}"
    assert dislikes == 0, f"Expected 0 dislikes (ghosted), got {dislikes}"
    
    print("✅ TEST PASSED: Hater's vote was successfully ghosted!")
    
    # 4. Cleanup
    await db.execute("DELETE FROM user_votes WHERE voted_id = $1", (voted_id,))
    await db.execute("DELETE FROM users WHERE telegram_id IN ($1, $2, $3)", (voted_id, hater_id, normal_id))
    await db.close()

if __name__ == "__main__":
    asyncio.run(run_test())
