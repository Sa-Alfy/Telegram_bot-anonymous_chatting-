import asyncpg
import os
import ssl
from contextlib import asynccontextmanager
from utils.logger import logger

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

class Database:
    _instance = None
    _pool: asyncpg.Pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    async def connect(self):
        """Initializes the database connection pool."""
        if self._pool is None:
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise ValueError("DATABASE_URL environment variable is not set. Required for Supabase Postgres.")
            
            # Use 'require' string for production to allow self-signed certificates (standard for Render/Supabase)
            ssl_mode = "require" if os.getenv("FLASK_ENV") != "development" else False
            
            self._pool = await asyncpg.create_pool(
                db_url,
                min_size=1,
                max_size=10,
                ssl=ssl_mode,
                command_timeout=30,
                max_inactive_connection_lifetime=300,
            )
            logger.info("Connected to PostgreSQL database pool (Supabase)")
            await self._init_db()

    async def _init_db(self):
        """Runs the schema.sql file to initialize tables."""
        if not os.path.exists(SCHEMA_PATH):
            logger.error(f"❌ Schema file not found at {SCHEMA_PATH}")
            return

        with open(SCHEMA_PATH, 'r') as f:
            schema = f.read()
            async with self._pool.acquire() as conn:
                await conn.execute(schema)
            logger.info("Database schema initialized.")

    async def _ensure_pool(self):
        if self._pool is None:
            await self.connect()

    async def execute(self, query: str, params: tuple = ()):
        """Executes a query.
        Returns a mock cursor-like object with a rowcount attribute for compatibility.
        """
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, *params)
            # asyncpg execute returns a status string like "UPDATE 1" or "INSERT 0 1"
            # We mock rowcount by parsing the last number in the string
            rowcount = 0
            try:
                rowcount = int(status.split()[-1])
            except (ValueError, IndexError, AttributeError):
                pass
            
            class MockCursor:
                def __init__(self, rc): self.rowcount = rc
            return MockCursor(rowcount)

    async def fetchone(self, query: str, params: tuple = ()):
        """Fetches a single row. Returns asyncpg.Record (dict-like)."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *params)

    async def fetchall(self, query: str, params: tuple = ()):
        """Fetches all rows. Returns list of asyncpg.Record (dict-like)."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *params)
            
    async def fetchval(self, query: str, params: tuple = ()):
        """Fetches a single value, useful for RETURNING clauses."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *params)

    async def close(self):
        """Closes the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed.")

    @asynccontextmanager
    async def transaction(self):
        """C10: Async context manager for atomic multi-statement transactions.
        Usage: async with db.transaction() as conn: await conn.execute(...)
        """
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

# Global instance
db = Database()
