# state/persistence.py
# This module is currently deprecated in favor of the unified Repository pattern.
# It is kept here for reference or future caching implementations.

import os
import asyncio
from utils.logger import logger
from database.connection import db

# In-memory cache stub (if needed)
user_profiles = {}

async def load_profiles():
    """Initializes the database connection (now handled by main startup)."""
    # This is a stub for backward compatibility
    pass

async def save_profiles(user_id: int = None):
    """Saves one or all profiles to the database."""
    # Logic moved to UserRepository
    pass
