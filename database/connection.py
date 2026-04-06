import aiosqlite
import os
from utils.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bot_database.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

class Database:
    _instance = None
    _connection: aiosqlite.Connection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    async def connect(self):
        """Initializes the database connection and creates tables if they don't exist."""
        if self._connection is None:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            
            self._connection = await aiosqlite.connect(DB_PATH)
            self._connection.row_factory = aiosqlite.Row
            # Enable high-concurrency WAL mode for production
            await self._connection.execute("PRAGMA journal_mode=WAL;")
            await self._connection.execute("PRAGMA synchronous=NORMAL;")
            
            logger.info(f"📁 Connected to database at {DB_PATH}")
            await self._init_db()

    async def _init_db(self):
        """Runs the schema.sql file to initialize tables."""
        if not os.path.exists(SCHEMA_PATH):
            logger.error(f"❌ Schema file not found at {SCHEMA_PATH}")
            return

        with open(SCHEMA_PATH, 'r') as f:
            schema = f.read()
            await self._connection.executescript(schema)
            await self._connection.commit()
            logger.info("✅ Database schema initialized.")

    async def execute(self, query: str, params: tuple = ()):
        """Executes a query and commits changes."""
        async with self._connection.execute(query, params) as cursor:
            await self._connection.commit()
            return cursor

    async def fetchone(self, query: str, params: tuple = ()):
        """Fetches a single row from a query."""
        async with self._connection.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """Fetches all rows from a query."""
        async with self._connection.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def close(self):
        """Closes the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("🔌 Database connection closed.")

# Global instance
db = Database()
