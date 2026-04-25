"""
===============================================================================
File: state/persistence.py
Description: [DEPRECATED] Legacy persistence module.

How it works:
This module previously handled direct database persistence for user profiles.
This logic has been completely replaced by the Repository pattern located in
'database/repositories/'.

Architecture & Patterns:
- Legacy Stub: Maintained only to prevent breakages in older import paths.

How to modify:
- DO NOT USE THIS FILE for new database logic.
- Use 'database/repositories/user_repository.py' for all user persistence.
===============================================================================
"""

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
